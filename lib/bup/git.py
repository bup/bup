"""Git interaction library.
bup repositories are in Git format. This library allows us to
interact with the Git data structures.
"""

import os, sys, zlib, subprocess, struct, stat, re, glob
from array import array
from binascii import hexlify, unhexlify
from contextlib import ExitStack
from dataclasses import replace
from itertools import islice
from shutil import rmtree
from subprocess import run
from sys import stderr
from typing import Optional, Union

from bup import _helpers, hashsplit, path, midx, bloom, xstat
from bup.commit import create_commit_blob, parse_commit
from bup.compat import dataclass, environ
from bup.io import path_msg
from bup.helpers import (EXIT_FAILURE,
                         OBJECT_EXISTS,
                         ObjectLocation,
                         Sha1, add_error, chunkyreader, debug1, debug2,
                         exo,
                         finalized,
                         fsync,
                         log,
                         make_repo_id,
                         merge_iter,
                         mmap_read, mmap_readwrite,
                         nullcontext_if_not,
                         progress, qprogress, stat_if_exists,
                         quote,
                         temp_dir,
                         unlink)
from bup.midx import open_midx


verbose = 0
repodir = None  # The default repository, once initialized

_typemap =  {b'blob': 3, b'tree': 2, b'commit': 1, b'tag': 4}
_typermap = {v: k for k, v in _typemap.items()}


_total_searches = 0
_total_steps = 0


class GitError(Exception):
    pass


def _gitenv(repo_dir=None):
    # This is not always used, i.e. sometimes we just use --git-dir
    if not repo_dir:
        repo_dir = repo()
    return {**environ, **{b'GIT_DIR': os.path.abspath(repo_dir)}}

def _git_wait(cmd, p):
    rv = p.wait()
    if rv != 0:
        raise GitError('%r returned %d' % (cmd, rv))

def _git_exo(cmd, **kwargs):
    kwargs['check'] = False
    result = exo(cmd, **kwargs)
    _, _, proc = result
    if proc.returncode != 0:
        raise GitError('%r returned %d' % (cmd, proc.returncode))
    return result

def repo_config_file(path):
    return os.path.join(path or repo(), b'config')

def git_config_get(path, option, *, opttype=None):
    cmd = [b'git', b'config', b'--file', path, b'--null']
    if opttype == 'int':
        cmd.extend([b'--int'])
    else:
        assert opttype in ('bool', None)
    cmd.extend([b'--get', option])
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, close_fds=True)
    # with --null, git writes out a trailing \0 after the value
    r = p.stdout.read()[:-1]
    rc = p.wait()
    if rc == 0:
        if opttype == 'int':
            return int(r)
        elif opttype == 'bool': # any positive int is true for git --bool
            if not r:
                return None
            if r in (b'0', b'false'):
                return False
            if r in (b'1', b'true'):
                return True
            raise GitError(f'{cmd!r} returned invalid boolean value {r}')
        return r
    if rc == 1:
        return None
    raise GitError('%r returned %d' % (cmd, rc))


def get_cat_data(cat_iterator, expected_type):
    _, kind, _ = next(cat_iterator)
    if kind != expected_type:
        raise Exception('expected %r, saw %r' % (expected_type, kind))
    return b''.join(cat_iterator)


def get_commit_items(id, cp):
    return parse_commit(get_cat_data(cp.get(id), b'commit'))


def repo(sub = b'', repo_dir=None):
    """Get the path to the git repository or one of its subdirectories."""
    repo_dir = repo_dir or repodir
    if not repo_dir:
        raise GitError('You should call check_repo_or_die()')

    # If there's a .git subdirectory, then the actual repo is in there.
    gd = os.path.join(repo_dir, b'.git')
    if os.path.exists(gd):
        repo_dir = gd

    return os.path.join(repo_dir, sub)


_shorten_hash_rx = \
    re.compile(br'([^0-9a-z]|\b)([0-9a-z]{7})[0-9a-z]{33}([^0-9a-z]|\b)')

def shorten_hash(s):
    return _shorten_hash_rx.sub(br'\1\2*\3', s)


def repo_rel(path):
    full = os.path.abspath(path)
    fullrepo = os.path.abspath(repo(b''))
    if not fullrepo.endswith(b'/'):
        fullrepo += b'/'
    if full.startswith(fullrepo):
        path = full[len(fullrepo):]
    if path.startswith(b'index-cache/'):
        path = path[len(b'index-cache/'):]
    return shorten_hash(path)


def auto_midx(objdir):
    args = [path.exe(), b'midx', b'--auto', b'--dir', objdir]
    try:
        rv = subprocess.call(args, stdout=open(os.devnull, 'w'))
    except OSError as e:
        # make sure 'args' gets printed to help with debugging
        add_error('%r: exception: %s' % (args, e))
        raise
    if rv:
        add_error('%r: returned %d' % (args, rv))

    args = [path.exe(), b'bloom', b'--dir', objdir]
    try:
        rv = subprocess.call(args, stdout=open(os.devnull, 'w'))
    except OSError as e:
        # make sure 'args' gets printed to help with debugging
        add_error('%r: exception: %s' % (args, e))
        raise
    if rv:
        add_error('%r: returned %d' % (args, rv))


def mangle_name(name, mode, gitmode):
    """Mangle a file name to present an abstract name for segmented files.
    Mangled file names will have the ".bup" extension added to them. If a
    file's name already ends with ".bup", a ".bupl" extension is added to
    disambiguate normal files from segmented ones.
    """
    if stat.S_ISREG(mode) and not stat.S_ISREG(gitmode):
        assert(stat.S_ISDIR(gitmode))
        return name + b'.bup'
    elif name.endswith(b'.bup') or name[:-1].endswith(b'.bup'):
        return name + b'.bupl'
    else:
        return name


(BUP_NORMAL, BUP_CHUNKED) = (0,1)
def demangle_name(name, mode):
    """Remove name mangling from a file name, if necessary.

    The return value is a tuple (demangled_filename,mode), where mode is one of
    the following:

    * BUP_NORMAL  : files that should be read as-is from the repository
    * BUP_CHUNKED : files that were chunked and need to be reassembled

    For more information on the name mangling algorithm, see mangle_name()
    """
    if name.endswith(b'.bupl'):
        return (name[:-5], BUP_NORMAL)
    elif name.endswith(b'.bup'):
        return (name[:-4], BUP_CHUNKED)
    elif name.endswith(b'.bupm'):
        return (name[:-5],
                BUP_CHUNKED if stat.S_ISDIR(mode) else BUP_NORMAL)
    elif name.endswith(b'.bupd'): # should be unreachable
        raise ValueError(f'Cannot unmangle *.bupd files: {path_msg(name)}')
    return (name, BUP_NORMAL)


def calc_hash(type, content):
    """Calculate some content's hash in the Git fashion."""
    header = b'%s %d\0' % (type, len(content))
    sum = Sha1(header)
    sum.update(content)
    return sum.digest()


def shalist_item_sort_key(ent):
    (mode, name, id) = ent
    assert(mode+0 == mode)
    if stat.S_ISDIR(mode):
        return name + b'/'
    else:
        return name


def tree_encode(shalist):
    """Generate a git tree object from (mode,name,hash) tuples."""
    shalist = sorted(shalist, key = shalist_item_sort_key)
    l = []
    for (mode,name,bin) in shalist:
        assert(mode)
        assert(mode+0 == mode)
        assert(name)
        assert(len(bin) == 20)
        s = b'%o %s\0%s' % (mode,name,bin)
        assert not s.startswith(b'0'), 'git trees do not allow 0-padded octal'
        l.append(s)
    return b''.join(l)


def tree_iter(tree_data):
    """Yield (mode, name, hash) for each entry in the git tree_data."""
    ofs = 0
    while ofs < len(tree_data):
        z = tree_data.find(b'\0', ofs)
        assert z > ofs
        mode_end = tree_data.find(b' ', ofs)
        name = tree_data[mode_end+1:z]
        mode = tree_data[ofs:mode_end]
        ofs = z + 21
        yield int(mode, 8), name, tree_data[z+1:z+1+20]


def tree_entries(tree_data):
    """Return a (mode, name, hash) list for the entries in the git
    tree_data.

    """
    result = []
    ofs = 0
    while ofs < len(tree_data):
        z = tree_data.find(b'\0', ofs)
        assert z > ofs
        mode_end = tree_data.find(b' ', ofs)
        name = tree_data[mode_end+1:z]
        mode = tree_data[ofs:mode_end]
        ent = int(mode, 8), name, tree_data[z+1:z+1+20]
        result.append(ent)
        ofs = z + 21
    return result


def find_tree_entry(named, tree_data):
    """Return mode, named, hash for the named entry in the git
    tree_data if it exists, or None.

    """
    assert not named.endswith(b'/')
    dirname = named + b'/'
    ofs = 0
    while ofs < len(tree_data):
        z = tree_data.find(b'\0', ofs)
        assert z > ofs
        mode_end = tree_data.find(b' ', ofs)
        name = tree_data[mode_end+1:z]
        # Both until min pylint is new enough
        # pylint: disable=consider-using-in
        # pylint: disable-next=consider-using-in
        if name == named or name == dirname:
            mode = tree_data[ofs:mode_end]
            ent = int(mode, 8), name, tree_data[z+1:z+1+20]
            return ent
        if name > dirname:
            break
        ofs = z + 21
    return None


def last_tree_entry(tree_data):
    oid_start = len(tree_data) - 20
    oid = tree_data[oid_start:]
    last_ent = 0
    z = 0
    while True:
        z = tree_data.find(b'\0', z)
        if z == -1:
            break
        z += 21
        if z < len(tree_data):
            last_ent = z
    mode_end = tree_data.find(b' ', last_ent)
    assert mode_end > 0
    mode = tree_data[last_ent:mode_end]
    name = tree_data[mode_end+1:oid_start-1]
    return int(mode, 8), name, oid


def _encode_packobj(type, content, compression_level=1):
    if compression_level not in range(-1, 10):
        raise ValueError('invalid compression level %s' % compression_level)
    szout = b''
    sz = len(content)
    szbits = (sz & 0x0f) | (_typemap[type]<<4)
    sz >>= 4
    while 1:
        if sz: szbits |= 0x80
        szout += szbits.to_bytes(1, 'big')
        if not sz:
            break
        szbits = sz & 0x7f
        sz >>= 7
    z = zlib.compressobj(compression_level)
    return szout, z.compress(content), z.flush()


def _decode_packobj(buf):
    assert(buf)
    c = buf[0]
    type = _typermap[(c & 0x70) >> 4]
    sz = c & 0x0f
    shift = 4
    i = 0
    while c & 0x80:
        i += 1
        c = buf[i]
        sz |= (c & 0x7f) << shift
        shift += 7
        if not (c & 0x80):
            break
    return (type, zlib.decompress(buf[i+1:]))


class PackIdx:
    def find_offset(self, hash):
        """Get the offset of an object inside the index file."""
        idx = self._idx_from_hash(hash)
        if idx != None:
            return self._ofs_from_idx(idx)
        return None

    def exists(self, hash, want_source=False, want_offset=False):
        """Return an ObjectLocation if the object exists in this
           index, otherwise None."""
        if not hash:
            return None
        idx = self._idx_from_hash(hash)
        if idx is not None:
            if want_source or want_offset:
                ret = ObjectLocation(None, None)
                if want_source:
                    ret.pack = os.path.basename(self.name)
                if want_offset:
                    ret.offset = self._ofs_from_idx(idx)
                return ret
            return OBJECT_EXISTS
        return None

    def _idx_from_hash(self, hash):
        global _total_searches, _total_steps
        _total_searches += 1
        assert(len(hash) == 20)
        b1 = hash[0]
        start = self.fanout[b1-1] # range -1..254
        end = self.fanout[b1] # range 0..255
        want = hash
        _total_steps += 1  # lookup table is a step
        while start < end:
            _total_steps += 1
            mid = start + (end - start) // 2
            v = self._idx_to_hash(mid)
            if v < want:
                start = mid+1
            elif v > want:
                end = mid
            else: # got it!
                return mid
        return None


class PackIdxV1(PackIdx):
    """Object representation of a Git pack index (version 1) file."""
    def __init__(self, filename, f):
        super().__init__()
        self.closed = False
        self.name = filename
        self.idxnames = [self.name]
        self.map = mmap_read(f)
        # Min size for 'L' is 4, which is sufficient for struct's '!I'
        self.fanout = array('L', struct.unpack('!256I', self.map))
        self.fanout.append(0)  # entry "-1"
        self.nsha = self.fanout[255]
        self.sha_ofs = 256 * 4
        # Avoid slicing shatable for individual hashes (very high overhead)
        assert self.nsha
        self.shatable = \
            memoryview(self.map)[self.sha_ofs:self.sha_ofs + self.nsha * 24]

    def __enter__(self): return self
    def __exit__(self, type, value, traceback): self.close()

    def __len__(self):
        return int(self.nsha)  # int() from long for python 2

    def _ofs_from_idx(self, idx):
        if idx >= self.nsha or idx < 0:
            raise IndexError('invalid pack index index %d' % idx)
        ofs = self.sha_ofs + idx * 24
        return struct.unpack_from('!I', self.map, offset=ofs)[0]

    def _idx_to_hash(self, idx):
        if idx >= self.nsha or idx < 0:
            raise IndexError('invalid pack index index %d' % idx)
        ofs = self.sha_ofs + idx * 24 + 4
        return self.map[ofs : ofs + 20]

    def __iter__(self):
        start = self.sha_ofs + 4
        for ofs in range(start, start + 24 * self.nsha, 24):
            yield self.map[ofs : ofs + 20]

    def oid_offsets_and_idxs(self):
        end = self.sha_ofs + self.nsha * 24
        for i, ofs in enumerate(range(self.sha_ofs, end, 24)):
            yield struct.unpack_from('!I', self.map, offset=ofs)[0], i

    def close(self):
        self.closed = True
        if self.map is not None:
            self.shatable = None
            self.map.close()
            self.map = None

    def __del__(self):
        assert self.closed


class PackIdxV2(PackIdx):
    """Object representation of a Git pack index (version 2) file."""
    def __init__(self, filename, f):
        super().__init__()
        self.closed = False
        self.name = filename
        self.idxnames = [self.name]
        self.map = mmap_read(f)
        assert self.map[0:8] == b'\377tOc\0\0\0\2'
        # Min size for 'L' is 4, which is sufficient for struct's '!I'
        self.fanout = array('L', struct.unpack_from('!256I', self.map, offset=8))
        self.fanout.append(0)
        self.nsha = self.fanout[255]
        self.sha_ofs = 8 + 256*4
        self.ofstable_ofs = self.sha_ofs + self.nsha * 20 + self.nsha * 4
        self.ofs64table_ofs = self.ofstable_ofs + self.nsha * 4
        # Avoid slicing this for individual hashes (very high overhead)
        assert self.nsha
        self.shatable = \
            memoryview(self.map)[self.sha_ofs:self.sha_ofs + self.nsha * 20]


    def __enter__(self): return self
    def __exit__(self, type, value, traceback): self.close()

    def __len__(self):
        return int(self.nsha)  # int() from long for python 2

    def _oid_ofs_from_ofs32_ofs(self, ofs32_ofs):
        ofs32 = struct.unpack_from('!I', self.map, offset=ofs32_ofs)[0]
        if ofs32 & 0x80000000:
            ofs64_i = ofs32 & 0x7fffffff
            ofs64_ofs = self.ofs64table_ofs + ofs64_i * 8
            return struct.unpack_from('!Q', self.map, offset=ofs64_ofs)[0]
        return ofs32

    def _ofs_from_idx(self, idx):
        if idx >= self.nsha or idx < 0:
            raise IndexError('invalid pack index index %d' % idx)
        ofs32_ofs = self.ofstable_ofs + idx * 4
        return self._oid_ofs_from_ofs32_ofs(ofs32_ofs)

    def _idx_to_hash(self, idx):
        if idx >= self.nsha or idx < 0:
            raise IndexError('invalid pack index index %d' % idx)
        ofs = self.sha_ofs + idx * 20
        return self.map[ofs : ofs + 20]

    def __iter__(self):
        start = self.sha_ofs
        for ofs in range(start, start + 20 * self.nsha, 20):
            yield self.map[ofs : ofs + 20]

    def close(self):
        self.closed = True
        if self.map is not None:
            self.shatable = None
            self.map.close()
            self.map = None

    def oid_offsets_and_idxs(self):
        end = self.ofstable_ofs + self.nsha * 4
        for i, ofs32_ofs in enumerate(range(self.ofstable_ofs, end, 4)):
            yield self._oid_ofs_from_ofs32_ofs(ofs32_ofs), i

    def __del__(self):
        assert self.closed


_mpi_count = 0
class PackIdxList:
    def __init__(self, dir, ignore_midx=False):
        global _mpi_count
        self.open = False # for __del__
        # Q: was this also intended to prevent opening multiple repos?
        assert(_mpi_count == 0) # these things suck tons of VM; don't waste it
        _mpi_count += 1
        self.open = True
        self.dir = dir
        self.packs = []
        self.do_bloom = False
        self.bloom = None
        self.ignore_midx = ignore_midx
        try:
            self.refresh()
        except BaseException as ex:
            self.close()
            raise ex

    def close(self):
        global _mpi_count
        if not self.open:
            assert _mpi_count == 0
            return
        _mpi_count -= 1
        assert _mpi_count == 0
        self.bloom, bloom = None, self.bloom
        self.packs, packs = None, self.packs
        self.open = False
        with ExitStack() as stack:
            for pack in packs:
                stack.enter_context(pack)
            if bloom:
                bloom.close()

    def __enter__(self): return self
    def __exit__(self, type, value, traceback): self.close()
    def __del__(self): assert not self.open

    def __iter__(self):
        return iter(idxmerge(self.packs))

    def __len__(self):
        return sum(len(pack) for pack in self.packs)

    def exists(self, hash, want_source=False, want_offset=False):
        """Return an ObjectLocation if the object exists in this
           index, otherwise None."""
        global _total_searches
        _total_searches += 1
        if self.do_bloom and self.bloom:
            if self.bloom.exists(hash):
                self.do_bloom = False
            else:
                _total_searches -= 1  # was counted by bloom
                return None
        for i in range(len(self.packs)):
            p = self.packs[i]
            if want_offset and isinstance(p, midx.PackMidx):
                get_src = True
                get_ofs = False
            else:
                get_src = want_source
                get_ofs = want_offset
            _total_searches -= 1  # will be incremented by sub-pack
            ret = p.exists(hash, want_source=get_src, want_offset=get_ofs)
            if ret:
                # reorder so most recently used packs are searched first
                self.packs = [p] + self.packs[:i] + self.packs[i+1:]
                if want_offset and ret.offset is None:
                    with open_idx(os.path.join(self.dir, ret.pack)) as np:
                        ret = np.exists(hash, want_source=want_source,
                                        want_offset=True)
                    assert ret
                return ret
        self.do_bloom = True
        return None

    def close_temps(self):
        '''
        Close all the temporary files (bloom/midx) so that you can safely call
        auto_midx() without potentially deleting files that are open/mapped.
        Note that you should call refresh() again afterwards to reload any new
        ones, otherwise performance will suffer.
        '''
        if self.bloom is not None:
            self.bloom.close()
            self.bloom = None
        for ix in list(self.packs):
            if not isinstance(ix, midx.PackMidx):
                continue
            ix.close()
            self.packs.remove(ix)

    def refresh(self, skip_midx = False):
        """Refresh the index list.
        This method verifies if .midx files were superseded (e.g. all of its
        contents are in another, bigger .midx file) and removes the superseded
        files.

        If skip_midx is True, all work on .midx files will be skipped and .midx
        files will be removed from the list.

        The instance variable 'ignore_midx' can force this function to
        always act as if skip_midx was True.
        """
        if self.bloom is not None:
            self.bloom.close()
        self.bloom = None # Always reopen the bloom as it may have been relaced
        self.do_bloom = False
        skip_midx = skip_midx or self.ignore_midx
        d = dict((p.name, p) for p in self.packs
                 if not skip_midx or not isinstance(p, midx.PackMidx))
        if os.path.exists(self.dir):
            if not skip_midx:
                midxl = []
                midxes = set(glob.glob(os.path.join(self.dir, b'*.midx')))
                # remove any *.midx files from our list that no longer exist
                for ix in list(d.values()):
                    if not isinstance(ix, midx.PackMidx):
                        continue
                    if ix.name in midxes:
                        continue
                    # remove the midx
                    del d[ix.name]
                    ix.close()
                    self.packs.remove(ix)
                for ix in self.packs:
                    if isinstance(ix, midx.PackMidx):
                        for name in ix.idxnames:
                            d[os.path.join(self.dir, name)] = ix
                for full in midxes:
                    if not d.get(full):
                        mx, missing = None, None
                        try:
                            mx = open_midx(full, ignore_missing=False)
                        except midx.MissingIdxs as ex:
                            missing = ex.paths
                        if not missing:
                            if mx: midxl.append(mx)
                        else:
                            mxd, mxf = os.path.split(full)
                            for n in missing:
                                log(('warning: index %s missing\n'
                                     '  used by %s\n')
                                    % (path_msg(n), path_msg(mxf)))
                            unlink(full)
                midxl.sort(key=lambda ix:
                           (-len(ix), -xstat.stat(ix.name).st_mtime))
                for ix in midxl:
                    any_needed = False
                    for sub in ix.idxnames:
                        found = d.get(os.path.join(self.dir, sub))
                        if not found or isinstance(found, PackIdx):
                            # doesn't exist, or exists but not in a midx
                            any_needed = True
                            break
                    if any_needed:
                        d[ix.name] = ix
                        for name in ix.idxnames:
                            d[os.path.join(self.dir, name)] = ix
                    else:
                        debug1('midx: removing redundant: %s\n'
                               % path_msg(os.path.basename(ix.name)))
                        ix.close()
                        unlink(ix.name)
            for full in glob.glob(os.path.join(self.dir, b'*.idx')):
                if not d.get(full):
                    try:
                        ix = open_idx(full)
                    except GitError as e:
                        add_error(e)
                        continue
                    d[full] = ix
            bfull = os.path.join(self.dir, b'bup.bloom')
            new_packs = set(d.values())
            for p in self.packs:
                if not p in new_packs:
                    p.close()
            new_packs = list(new_packs)
            new_packs.sort(reverse=True, key=lambda x: len(x))
            self.packs = new_packs
            if self.bloom is None and os.path.exists(bfull):
                self.bloom = bloom.ShaBloom(bfull)
            try:
                if self.bloom and self.bloom.valid() and len(self.bloom) >= len(self):
                    self.do_bloom = True
                else:
                    if self.bloom:
                        self.bloom, bloom_tmp = None, self.bloom
                        bloom_tmp.close()
            except BaseException as ex:
                if self.bloom:
                    self.bloom.close()
                raise ex

        debug1('PackIdxList: using %d index%s.\n'
            % (len(self.packs), len(self.packs)!=1 and 'es' or ''))


def open_idx(filename):
    if not filename.endswith(b'.idx'): # why is this enforced *here*?
        raise GitError('pack idx filenames must end with .idx')
    f = open(filename, 'rb')
    with ExitStack() as contexts:
        contexts.enter_context(f)
        header = f.read(8)
        if header[0:4] == b'\377tOc':
            version = struct.unpack('!I', header[4:8])[0]
            if version == 2:
                contexts.pop_all()
                return PackIdxV2(filename, f)
            else:
                raise GitError('%s: expected idx file version 2, got %d'
                               % (path_msg(filename), version))
        elif len(header) == 8 and header[0:4] < b'\377tOc':
            contexts.pop_all()
            return PackIdxV1(filename, f)
        else:
            raise GitError('%s: unrecognized idx file header'
                           % path_msg(filename))


def open_object_idx(filename):
    if filename.endswith(b'.idx'):
        return open_idx(filename)
    elif filename.endswith(b'.midx'):
        return open_midx(filename)
    else:
        raise GitError('pack index filenames must end with .idx or .midx')


def idxmerge(idxlist, final_progress=True):
    """Generate a list of all the objects reachable in a PackIdxList."""
    def pfunc(count, total):
        qprogress('Reading indexes: %.2f%% (%d/%d)\r'
                  % (count*100.0/total, count, total))
    def pfinal(count, total):
        if final_progress:
            progress('Reading indexes: %.2f%% (%d/%d), done.\n'
                     % (100, total, total))
    return merge_iter(idxlist, 10024, pfunc, pfinal)


# del/exit/close/etc. wrt parent/child?

class LocalPackStore():

    def __init__(self, *, allow_duplicates=False, on_pack_finish=None,
                 repo_dir=None, run_midx=True):
        """When allow_duplicates is false, (at some cost) avoid
        writing duplicates of objects that already in the repository.

        """
        self._closed = False
        self._file = None
        self._idx = None
        self._deduplicate_writes = not allow_duplicates
        self._obj_count = 0
        self._objcache = None
        self._on_pack_finish = on_pack_finish
        self._parentfd = None
        self._repo_dir = repo_dir or repo()
        self._run_midx=run_midx
        self._tmpdir = None

    def __del__(self): assert self._closed

    def exists(self, oid, want_source=False):
        """Return a true value if the oid is found in the object
        cache. When want_source is true, return the source if
        available.

        """
        if self._objcache is None:
            self._objcache = \
                PackIdxList(repo(b'objects/pack', repo_dir=self._repo_dir))
        return self._objcache.exists(oid, want_source=want_source)

    def _open(self):
        if not self._file:
            with ExitStack() as err_stack:
                objdir = dir = os.path.join(self._repo_dir, b'objects')
                self._tmpdir = err_stack.enter_context(temp_dir(dir=objdir, prefix=b'pack-tmp-'))
                self._file = err_stack.enter_context(open(self._tmpdir + b'/pack', 'w+b'))
                self._parentfd = err_stack.enter_context(finalized(os.open(objdir, os.O_RDONLY),
                                                                   lambda x: os.close(x)))
                self._file.write(b'PACK\0\0\0\2\0\0\0\0')
                self._idx = PackIdxV2Writer()
                err_stack.pop_all()

    def _update_idx(self, sha, crc, size):
        assert(sha)
        if self._idx:
            self._idx.add(sha, crc, self._file.tell() - size)

    def write(self, datalist, sha):
        self._open()
        f = self._file
        # in case we get interrupted (eg. KeyboardInterrupt), it's best if
        # the file never has a *partial* blob.  So let's make sure it's
        # all-or-nothing.  (The blob shouldn't be very big anyway, thanks
        # to our hashsplit algorithm.)  f.write() does its own buffering,
        # but that's okay because we'll flush it in _end().
        oneblob = b''.join(datalist)
        try:
            f.write(oneblob)
        except IOError as e:
            raise GitError(e) from e
        nw = len(oneblob)
        crc = zlib.crc32(oneblob) & 0xffffffff
        self._update_idx(sha, crc, nw)
        self._obj_count += 1
        return nw, crc

    def finish_pack(self, *, abort=False):
        # Ignores run_midx during abort
        self._tmpdir, tmpdir = None, self._tmpdir
        self._parentfd, pfd, = None, self._parentfd
        self._file, f = None, self._file
        self._idx, idx = None, self._idx
        try:
            with nullcontext_if_not(self._objcache), \
                 finalized(pfd, lambda x: x is not None and os.close(x)), \
                 nullcontext_if_not(f):
                if abort or not f:
                    return None

                # update object count
                f.seek(8)
                cp = struct.pack('!i', self._obj_count)
                assert len(cp) == 4
                f.write(cp)

                # calculate the pack sha1sum
                f.seek(0)
                sum = Sha1()
                for b in chunkyreader(f):
                    sum.update(b)
                packbin = sum.digest()
                f.write(packbin)
                f.flush()
                fsync(f.fileno())
                f.close()

                idx.write(tmpdir + b'/idx', packbin)
                nameprefix = os.path.join(self._repo_dir,
                                          b'objects/pack/pack-' +  hexlify(packbin))
                os.rename(tmpdir + b'/pack', nameprefix + b'.pack')
                os.rename(tmpdir + b'/idx', nameprefix + b'.idx')
                fsync(pfd)
                if self._on_pack_finish:
                    self._on_pack_finish(nameprefix)
                if self._run_midx:
                    auto_midx(os.path.join(self._repo_dir, b'objects/pack'))
                return nameprefix
        finally:
            self._obj_count = 0
            self._objcache = None # last -- some code above depends on it
            if tmpdir:
                rmtree(tmpdir)

    def abort(self):
        self._closed = True
        self.finish_pack(abort=True)

    def close(self):
        self._closed = True
        return self.finish_pack()


# bup-gc assumes that it can disable all PackWriter activities
# (bloom/midx/cache) via the constructor and close() arguments.


class PackWriter:
    """Write Git objects to pack files."""

    def __init__(self, *, store, compression_level=None,
                 max_pack_size=None, max_pack_objects=None):
        self._byte_count = 0
        self._obj_count = 0
        self._store = store
        self._pending_oids = set()
        if compression_level is None:
            compression_level = 1
        self.compression_level = compression_level
        self.max_pack_size = max_pack_size or 1000 * 1000 * 1000
        # cache memory usage is about 83 bytes per object
        self.max_pack_objects = max_pack_objects if max_pack_objects \
                                else max(1, self.max_pack_size // 5000)

    def __enter__(self): return self
    def __exit__(self, type, value, traceback): self.close()

    def byte_count(self): return self._byte_count
    def object_count(self): return self._obj_count

    def _write(self, sha, type, content):
        if verbose:
            log('>')
        assert sha
        encoded = _encode_packobj(type, content, self.compression_level)
        size, crc = self._store.write(encoded, sha=sha)
        self._byte_count += sum(len(x) for x in encoded)
        self._obj_count += 1
        if self._byte_count >= self.max_pack_size \
           or self._obj_count >= self.max_pack_objects:
            self.breakpoint()
        return sha

    def exists(self, oid, want_source=False):
        """Return non-empty if an object is found in the object cache."""
        return oid in self._pending_oids \
            or self._store.exists(oid, want_source=want_source)

    def just_write(self, sha, type, content):
        """Write an object to the pack file without deduplication."""
        self._write(sha, type, content)
        self._pending_oids.add(sha)

    def maybe_write(self, type, content):
        """Write an object to the pack file if not present and return its id."""
        sha = calc_hash(type, content)
        if not self.exists(sha):
            self._write(sha, type, content)
            self._pending_oids.add(sha)
        return sha

    def new_blob(self, blob):
        """Create a blob object in the pack with the supplied content."""
        return self.maybe_write(b'blob', blob)

    def new_tree(self, shalist):
        """Create a tree object in the pack."""
        content = tree_encode(shalist)
        return self.maybe_write(b'tree', content)

    def new_commit(self, tree, parent,
                   author, adate_sec, adate_tz,
                   committer, cdate_sec, cdate_tz,
                   msg):
        """Create a commit object in the pack.  The date_sec values
        must be epoch-seconds, and if a tz is None, the local timezone
        is assumed. Return the commit oid.

        """
        content = create_commit_blob(tree, parent,
                                     author, adate_sec, adate_tz,
                                     committer, cdate_sec, cdate_tz,
                                     msg)
        return self.maybe_write(b'commit', content)

    def abort(self):
        """Remove the pack file from disk."""
        self._store.abort()

    def breakpoint(self):
        """Clear byte and object counts and return the last processed id."""
        result = self._store.finish_pack()
        self._byte_count = self._obj_count = 0
        return result

    def close(self):
        """Close the pack file and move it to its definitive path."""
        return self._store.close()


class PackIdxV2Writer:
    def __init__(self):
        self.idx = list(list() for i in range(256))
        self.count = 0

    def add(self, sha, crc, offs):
        assert(sha)
        self.count += 1
        self.idx[sha[0]].append((sha, crc, offs))

    def write(self, filename, packbin):
        ofs64_count = 0
        for section in self.idx:
            for entry in section:
                if entry[2] >= 2**31:
                    ofs64_count += 1

        # Length: header + fan-out + shas-and-crcs + overflow-offsets
        index_len = 8 + (4 * 256) + (28 * self.count) + (8 * ofs64_count)
        idx_map = None
        idx_f = open(filename, 'w+b')
        try:
            idx_f.truncate(index_len)
            fsync(idx_f.fileno())
            idx_map = mmap_readwrite(idx_f, close=False)
            try:
                count = _helpers.write_idx(filename, idx_map, self.idx,
                                           self.count)
                assert(count == self.count)
                idx_map.flush()
            finally:
                idx_map.close()
        finally:
            idx_f.close()

        idx_f = open(filename, 'a+b')
        try:
            idx_f.write(packbin)
            idx_f.seek(0)
            idx_sum = Sha1()
            b = idx_f.read(8 + 4*256)
            idx_sum.update(b)

            for b in chunkyreader(idx_f, 20 * self.count):
                idx_sum.update(b)

            for b in chunkyreader(idx_f):
                idx_sum.update(b)
            idx_f.write(idx_sum.digest())
            fsync(idx_f.fileno())
        finally:
            idx_f.close()


def list_refs(patterns=None, repo_dir=None,
              limit_to_heads=False, limit_to_tags=False):
    """Yield (refname, hash) tuples for all repository refs unless
    patterns are specified.  In that case, only include tuples for
    refs matching those patterns (cf. git-show-ref(1)).  The limits
    restrict the result items to refs/heads or refs/tags.  If both
    limits are specified, items from both sources will be included.

    """
    argv = [b'git', b'show-ref']
    if limit_to_heads:
        argv.append(b'--heads')
    if limit_to_tags:
        argv.append(b'--tags')
    argv.append(b'--')
    if patterns:
        argv.extend(patterns)
    p = subprocess.Popen(argv, env=_gitenv(repo_dir), stdout=subprocess.PIPE,
                         close_fds=True)
    out = p.stdout.read().strip()
    rv = p.wait()  # not fatal
    if rv:
        assert(not out)
    if out:
        for d in out.split(b'\n'):
            sha, name = d.split(b' ', 1)
            yield name, unhexlify(sha)


def read_ref(refname, repo_dir = None):
    """Get the commit id of the most recent commit made on a given ref."""
    refs = list_refs(patterns=[refname], repo_dir=repo_dir, limit_to_heads=True)
    l = tuple(islice(refs, 2))
    if l:
        assert(len(l) == 1)
        return l[0][1]
    else:
        return None


def rev_list_invocation(ref_or_refs, format=None):
    if isinstance(ref_or_refs, bytes):
        refs = (ref_or_refs,)
    else:
        refs = ref_or_refs
    argv = [b'git', b'rev-list']

    if format:
        argv.append(b'--pretty=format:' + format)
    for ref in refs:
        assert not ref.startswith(b'-')
        argv.append(ref)
    argv.append(b'--')
    return argv


def rev_list(ref_or_refs, parse=None, format=None, repo_dir=None):
    """Yield information about commits as per "git rev-list".  If a format
    is not provided, yield one hex hash at a time.  If a format is
    provided, pass it to rev-list and call parse(git_stdout) for each
    commit with the stream positioned just after the rev-list "commit
    HASH" header line.  When a format is provided yield (oidx,
    parse(git_stdout)) for each commit.

    """
    assert bool(parse) == bool(format)
    p = subprocess.Popen(rev_list_invocation(ref_or_refs,
                                             format=format),
                         env=_gitenv(repo_dir),
                         stdout = subprocess.PIPE,
                         close_fds=True)
    if not format:
        for line in p.stdout:
            yield line.strip()
    else:
        line = p.stdout.readline()
        while line:
            s = line.strip()
            if not s.startswith(b'commit '):
                raise Exception('unexpected line ' + repr(s))
            s = s[7:]
            assert len(s) == 40
            yield s, parse(p.stdout)
            line = p.stdout.readline()

    rv = p.wait()  # not fatal
    if rv:
        raise GitError('git rev-list returned error %d' % rv)


def rev_parse(committish, repo_dir=None):
    """Resolve the full hash for 'committish', if it exists.

    Should be roughly equivalent to 'git rev-parse'.

    Returns the hex value of the hash if it is found, None if 'committish' does
    not correspond to anything.
    """
    head = read_ref(committish, repo_dir=repo_dir)
    if head:
        debug2(f'resolved from ref: commit = {head.hex()}\n')
        return head

    if len(committish) == 40:
        try:
            hash = unhexlify(committish)
        except TypeError:
            return None

        with PackIdxList(repo(b'objects/pack', repo_dir=repo_dir)) as pL:
            if pL.exists(hash):
                return hash

    return None


def update_ref(refname, newval, oldval, repo_dir=None, force=False):
    """Update a repository reference.

    With force=True, don't care about the previous ref (oldval);
    with force=False oldval must be either a sha1 or None (for an
    entirely new branch)
    """
    if force:
        assert oldval is None
        oldarg = []
    elif not oldval:
        oldarg = [b'']
    else:
        oldarg = [hexlify(oldval)]
    assert refname.startswith(b'refs/heads/') \
        or refname.startswith(b'refs/tags/')
    cmd = [b'git', b'update-ref', refname, hexlify(newval)] + oldarg
    p = subprocess.Popen(cmd, env=_gitenv(repo_dir), close_fds=True)
    _git_wait(b' '.join(quote(x) for x in cmd), p)


def delete_ref(refname, oldvalue=None):
    """Delete a repository reference (see git update-ref(1))."""
    assert refname.startswith(b'refs/')
    oldvalue = [] if not oldvalue else [oldvalue]
    cmd = [b'git', b'update-ref', b'-d', refname] + oldvalue
    p = subprocess.Popen(cmd, env=_gitenv(), close_fds=True)
    _git_wait(b' '.join(quote(x) for x in cmd), p)


def guess_repo():
    """Return the global repodir or BUP_DIR when either is set, or ~/.bup.
    Usually, if you are interacting with a bup repository, you would
    not be calling this function but using check_repo_or_die().

    """
    # previously set?
    if repodir:
        return repodir
    return path.defaultrepo()


def init_repo(path=None):
    """Create the Git bare repository for bup in a given path."""
    global repodir
    repodir = path or guess_repo()
    d = repo()  # appends a / to the path
    parent = os.path.dirname(os.path.dirname(d))
    if parent and not os.path.exists(parent):
        raise GitError('parent directory "%s" does not exist\n'
                       % path_msg(parent))
    if os.path.exists(d) and not os.path.isdir(os.path.join(d, b'.')):
        raise GitError('"%s" exists but is not a directory\n' % path_msg(d))
    # This is how git detects existing repos
    refresh = os.path.exists(os.path.join(d, b'HEAD'))
    p = subprocess.Popen([ b'git', b'--bare',
                           # arbitrary default branch name to suppress git msg.
                           b'-c', b'init.defaultBranch=main', b'init'],
                         stdout=sys.stderr,
                         env=_gitenv(),
                         close_fds=True)
    _git_wait('git init', p)

    cfg = os.path.join(d, b'config')
    def get_config(*arg, **kwargs):
        return git_config_get(cfg, *arg, **kwargs)
    def set_config(opt, val):
        cp = run([b'git', b'config', opt, val], stdout=stderr, env=_gitenv())
        if cp.returncode:
            raise GitError(f'git config {opt} {val} exited with {cp.returncode}')

    # Always set the indexVersion so bup works with any git version
    if refresh:
        if get_config(b'bup.repo.id') is None:
            set_config(b'bup.repo.id', make_repo_id())
        if get_config(b'pack.indexVersion', opttype='int') != 2:
            set_config(b'pack.indexVersion', b'2')
    else: # "no repo" (see above), reestablish defaults (as git does)
        set_config(b'bup.repo.id', make_repo_id())
        set_config(b'core.logAllRefUpdates', b'true'), # enable the reflog
        set_config(b'pack.indexVersion', b'2')


def establish_default_repo(path=None, *, must_exist=False):
    """If path (defaults to guess_repo()) is valid, make it the
    default repository and return True.  If path isn't valid (because
    it doesn't exist or doesn't appear to be a repository), either
    exit() with an error status if must_exist is true or return False.

    """
    global repodir
    repodir = path or guess_repo()
    top = repo()
    pst = stat_if_exists(top + b'/objects/pack')
    if pst and stat.S_ISDIR(pst.st_mode):
        return True
    if not pst:
        top_st = stat_if_exists(top)
        if not top_st:
            if must_exist:
                log('error: repository %r does not exist (see "bup help init")\n'
                    % top)
                sys.exit(15)
            return False
    if must_exist:
        log('error: %s is not a repository\n' % path_msg(top))
        sys.exit(14)
    return False

def check_repo_or_die(path=None):
    """Equivalent to git.establish_default_repo(path, must_exist=True)."""
    establish_default_repo(path, must_exist=True)


def is_suitable_git(ver_str):
    if not ver_str.startswith(b'git version '):
        return 'unrecognized'
    ver_str = ver_str[len(b'git version '):]
    if ver_str.startswith(b'0.'):
        return 'insufficient'
    if ver_str.startswith(b'1.'):
        if re.match(br'1\.[01234567]rc', ver_str):
            return 'insufficient'
        if re.match(br'1\.[0123456]\.', ver_str):
            return 'insufficient'
        if re.match(br'1\.7\.[01]($|\.)', ver_str):
            return 'insufficient'
        if re.match(br'1\.7\.2-rc', ver_str):
            return 'insufficient'
        return 'suitable'
    if re.match(br'[0-9]+(\.|$)?', ver_str):
        return 'suitable'
    sys.exit(13)

_git_great = None

def require_suitable_git(ver_str=None):
    """Raise GitError if the version of git isn't suitable.

    Rely on ver_str when provided, rather than invoking the git in the
    path.

    """
    global _git_great
    if _git_great is not None:
        return
    if environ.get(b'BUP_GIT_VERSION_IS_FINE', b'').lower() \
       in (b'yes', b'true', b'1'):
        _git_great = True
        return
    if not ver_str:
        ver_str, _, _ = _git_exo([b'git', b'--version'])
    status = is_suitable_git(ver_str)
    if status == 'unrecognized':
        raise GitError('Unexpected git --version output: %r' % ver_str)
    if status == 'insufficient':
        log('error: git version must be at least 1.7.2\n')
        sys.exit(EXIT_FAILURE)
    if status == 'suitable':
        _git_great = True
        return
    assert False


class CatPipe:
    """Link to 'git cat-file' that is used to retrieve blob data."""
    def __init__(self, repo_dir = None):
        require_suitable_git()
        self.repo_dir = repo_dir
        self.p = self.pcheck = self.inprogress = None

        # probe for cat-file --batch-command
        tmp = subprocess.Popen([b'git', b'cat-file', b'--batch-command'],
                               stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,
                               close_fds=True,
                               env=_gitenv(self.repo_dir))
        tmp.wait();
        self.have_batch_command = tmp.returncode == 0

    def close(self, wait=False):
        self.p, p = None, self.p
        self.pcheck, pcheck = None, self.pcheck
        self.inprogress = None
        if p:
            try:
                p.stdout.close()
            finally:
                p.stdin.close()
        if pcheck and pcheck != p:
            try:
                pcheck.stdout.close()
            finally:
                pcheck.stdin.close()
        if wait:
            if p: p.wait()
            if pcheck: pcheck.wait()
            if p and p.returncode:
                return p.returncode
            if pcheck and pcheck.returncode:
                return pcheck.returncode
            return 0
        return None

    def restart(self):
        self.close()
        self.p = subprocess.Popen([b'git', b'cat-file',
                                  b'--batch-command' if self.have_batch_command else b'--batch'],
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  close_fds = True,
                                  bufsize = 4096,
                                  env=_gitenv(self.repo_dir))

    def _open_check(self):
        if self.pcheck is not None: return
        if self.have_batch_command:
            self.pcheck = self.p
            return
        self.pcheck = subprocess.Popen([b'git', b'cat-file', b'--batch-check'],
                                       stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE,
                                       close_fds = True,
                                       bufsize = 4096,
                                       env=_gitenv(self.repo_dir))

    def get(self, ref, include_data=True):
        """Yield (oidx, type, size), followed by the data referred to by ref.
        If ref does not exist, only yield (None, None, None).

        """
        if not self.p or self.p.poll() != None:
            self.restart()
        assert(self.p)
        poll_result = self.p.poll()
        assert poll_result is None
        assert not self.inprogress, \
            f'opening {ref.decode("ascii")} while {self.inprogress.decode("ascii")} is open'
        assert ref.find(b'\n') < 0
        assert ref.find(b'\r') < 0
        assert not ref.startswith(b'-')
        self.inprogress = ref
        if include_data:
            p = self.p
            if self.have_batch_command:
                p.stdin.write(b'contents ')
        else:
            self._open_check()
            p = self.pcheck
            if self.have_batch_command:
                p.stdin.write(b'info ')
        p.stdin.write(ref + b'\n')
        p.stdin.flush()
        hdr = p.stdout.readline()
        if not hdr:
            raise GitError('unexpected cat-file EOF (last request: %r, exit: %s)'
                           % (ref, p.poll() or 'none'))
        if hdr.endswith(b' missing\n'):
            self.inprogress = None
            yield None, None, None
            return
        info = hdr.split(b' ')
        if len(info) != 3 or len(info[0]) != 40:
            raise GitError('expected object (id, type, size), got %r' % info)
        oidx, typ, size = info
        size = int(size)

        if not include_data:
            self.inprogress = None
            yield oidx, typ, size
            return

        try:
            yield oidx, typ, size
            for blob in chunkyreader(p.stdout, size):
                yield blob
            readline_result = p.stdout.readline()
            assert readline_result == b'\n'
            self.inprogress = None
        except Exception as ex:
            self.close()
            raise ex


_cp = {}

def cp(repo_dir=None):
    """Create a CatPipe object or reuse the already existing one."""
    global _cp, repodir
    if not repo_dir:
        repo_dir = repodir or repo()
    repo_dir = os.path.abspath(repo_dir)
    cp = _cp.get(repo_dir)
    if not cp:
        cp = CatPipe(repo_dir)
        _cp[repo_dir] = cp
    return cp


def close_catpipes():
    # FIXME: chain exceptions
    while _cp:
        _, cp = _cp.popitem()
        cp.close(wait=True)


def tags(repo_dir = None):
    """Return a dictionary of all tags in the form {hash: [tag_names, ...]}."""
    tags = {}
    for n, c in list_refs(repo_dir = repo_dir, limit_to_tags=True):
        assert n.startswith(b'refs/tags/')
        name = n[10:]
        if not c in tags:
            tags[c] = []
        tags[c].append(name)  # more than one tag can point at 'c'
    return tags


class MissingObject(KeyError):
    __slots__ = 'oid',
    def __init__(self, oid):
        self.oid = oid
        KeyError.__init__(self, f'object {hexlify(oid)!r} is missing')


@dataclass(slots=True, frozen=True)
class WalkItem:
    oid: bytes
    name: bytes
    type: Union['blob', 'commit', 'tree']
    mode: int
    data: Optional[bytes]

def walk_object(get_ref, oidx, *, stop_at=None, include_data=None,
                oid_exists=None, result='path'):
    """Yield everything reachable from oidx via get_ref (which must
    behave like CatPipe get) as a path, which is a list of WalkItems,
    stopping whenever stop_at(oidx) returns logically true.  Set the
    data field to False when the object is missing, or None if the
    object exists but include_data is logically false.  Missing blobs
    may not be noticed unless include_data is logically true or
    oid_exists(oid) is provided.  Yield items depth first, post-order,
    i.e. parents after children. A tree will be yielded (later) if
    stop_item(oidx) is false when it is first encountered.

    The data will be None for all path items except the last.

    """

    assert result in ('path', 'item')

    # Maintain the pending stack on the heap to avoid stack overflow
    pending = [(False, oidx, [], oidx, None, None)]
    while len(pending):
        completed_item = pending[-1][0]
        assert completed_item in (True, False)
        if completed_item:
            yield pending.pop()[1]
            continue

        _, oidx, parents, name, mode, exp_typ = pending.pop()
        if stop_at and stop_at(oidx):
            continue

        oid = unhexlify(oidx)

        if (not include_data) and mode and exp_typ == b'blob':
            # If the object is a "regular file", then it's a leaf in
            # the graph, so we can skip reading the data if the caller
            # hasn't requested it.
            item = WalkItem(oid=oid, type=b'blob', name=name, mode=mode,
                            data=bool(oid_exists(oid)) if oid_exists else None)
            yield [*parents, item] if result == 'path' else item
            continue

        if exp_typ in (b'commit', b'tree', None): # must have the data
            item_it = get_ref(oidx, include_data=True)
        else:
            item_it = get_ref(oidx, include_data=include_data)
        get_oidx, typ, _ = next(item_it)
        if not get_oidx:
            item = WalkItem(oid=unhexlify(oidx), type=exp_typ, name=name,
                            mode=mode, data=False)
            yield [*parents, item] if result == 'path' else item
            continue
        if typ not in (b'blob', b'commit', b'tree'):
            raise Exception('unexpected repository object type %r' % typ)
        if exp_typ and typ != exp_typ:
            raise Exception(f'{oidx.decode("ascii")} object type {typ} != {exp_typ}')

        # FIXME: set the mode based on the type when the mode is None
        if typ == b'blob' and not include_data:
            data = None
        else:
            data = b''.join(item_it)

        item = WalkItem(oid=oid, type=typ, mode=mode, name=name,
                        data=(data if include_data else None))
        res = [*parents, item] if result == 'path' else item

        if typ == b'blob':
            yield res
        elif typ == b'commit':
            pending.append((True, res))
            commit = parse_commit(data)
            commit_path = [*parents, replace(item, data=None)]
            for pid in commit.parents:
                pending.append((False, pid, commit_path, pid, mode, b'commit'))
            pending.append((False, commit.tree, parents, commit.tree,
                            hashsplit.GIT_MODE_TREE, b'tree'))
        elif typ == b'tree':
            pending.append((True, res))
            tree_path = [*parents, replace(item, data=None)]
            for mode, name, ent_id in tree_iter(data):
                pending.append((False, hexlify(ent_id), tree_path, name, mode,
                                b'tree' if stat.S_ISDIR(mode) else b'blob'))
