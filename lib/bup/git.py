"""Git interaction library.
bup repositories are in Git format. This library allows us to
interact with the Git data structures.
"""

from __future__ import absolute_import, print_function
import os, sys, zlib, subprocess, struct, stat, re, glob
from array import array
from binascii import hexlify, unhexlify
from collections import namedtuple
from contextlib import ExitStack
from itertools import islice
from shutil import rmtree

from bup import _helpers, hashsplit, path, midx, bloom, xstat
from bup.compat import (buffer,
                        byte_int, bytes_from_byte, bytes_from_uint,
                        environ,
                        pending_raise)
from bup.io import path_msg
from bup.helpers import (Sha1, add_error, chunkyreader, debug1, debug2,
                         exo,
                         fdatasync,
                         finalized,
                         log,
                         merge_dict,
                         merge_iter,
                         mmap_read, mmap_readwrite,
                         nullcontext_if_not,
                         progress, qprogress, stat_if_exists,
                         temp_dir,
                         unlink,
                         utc_offset_str)
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
    return merge_dict(environ, {b'GIT_DIR': os.path.abspath(repo_dir)})

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

def git_config_get(option, repo_dir=None, opttype=None, cfg_file=None):
    assert not (repo_dir and cfg_file), "repo_dir and cfg_file cannot both be used"
    if cfg_file:
        cmd = [b'git', b'config', b'--file', cfg_file, b'--null']
    else:
        cmd = [b'git', b'--git-dir', repo_dir or repo(), b'config', b'--null']
    if opttype == 'int':
        cmd.extend([b'--int'])
    elif opttype == 'bool':
        cmd.extend([b'--bool'])
    else:
        assert opttype is None
    cmd.extend([b'--get', option])
    env=None
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, close_fds=True)
    # with --null, git writes out a trailing \0 after the value
    r = p.stdout.read()[:-1]
    rc = p.wait()
    if rc == 0:
        if opttype == 'int':
            return int(r)
        elif opttype == 'bool':
            # git converts to 'true' or 'false'
            return r == b'true'
        return r
    if rc != 1:
        raise GitError('%r returned %d' % (cmd, rc))
    return None


def parse_tz_offset(s):
    """UTC offset in seconds."""
    tz_off = (int(s[1:3]) * 60 * 60) + (int(s[3:5]) * 60)
    if bytes_from_byte(s[0]) == b'-':
        return - tz_off
    return tz_off

def parse_commit_gpgsig(sig):
    """Return the original signature bytes.

    i.e. with the "gpgsig " header and the leading space character on
    each continuation line removed.

    """
    if not sig:
        return None
    assert sig.startswith(b'gpgsig ')
    sig = sig[7:]
    return sig.replace(b'\n ', b'\n')

# FIXME: derived from http://git.rsbx.net/Documents/Git_Data_Formats.txt
# Make sure that's authoritative.

# See also
# https://github.com/git/git/blob/master/Documentation/technical/signature-format.txt
# The continuation lines have only one leading space.

_start_end_char = br'[^ .,:;<>"\'\0\n]'
_content_char = br'[^\0\n<>]'
_safe_str_rx = br'(?:%s{1,2}|(?:%s%s*%s))' \
    % (_start_end_char,
       _start_end_char, _content_char, _start_end_char)
_tz_rx = br'[-+]\d\d[0-5]\d'
_parent_rx = br'(?:parent [abcdefABCDEF0123456789]{40}\n)'
# Assumes every following line starting with a space is part of the
# mergetag.  Is there a formal commit blob spec?
_mergetag_rx = br'(?:\nmergetag object [abcdefABCDEF0123456789]{40}(?:\n [^\0\n]*)*)'
_commit_rx = re.compile(br'''tree (?P<tree>[abcdefABCDEF0123456789]{40})
(?P<parents>%s*)author (?P<author_name>%s) <(?P<author_mail>%s)> (?P<asec>\d+) (?P<atz>%s)
committer (?P<committer_name>%s) <(?P<committer_mail>%s)> (?P<csec>\d+) (?P<ctz>%s)(?P<mergetag>%s?)
(?P<gpgsig>gpgsig .*\n(?: .*\n)*)?
(?P<message>(?:.|\n)*)''' % (_parent_rx,
                             _safe_str_rx, _safe_str_rx, _tz_rx,
                             _safe_str_rx, _safe_str_rx, _tz_rx,
                             _mergetag_rx))
_parent_hash_rx = re.compile(br'\s*parent ([abcdefABCDEF0123456789]{40})\s*')

# Note that the author_sec and committer_sec values are (UTC) epoch
# seconds, and for now the mergetag is not included.
CommitInfo = namedtuple('CommitInfo', ['tree', 'parents',
                                       'author_name', 'author_mail',
                                       'author_sec', 'author_offset',
                                       'committer_name', 'committer_mail',
                                       'committer_sec', 'committer_offset',
                                       'gpgsig',
                                       'message'])

def parse_commit(content):
    commit_match = re.match(_commit_rx, content)
    if not commit_match:
        raise Exception('cannot parse commit %r' % content)
    matches = commit_match.groupdict()
    return CommitInfo(tree=matches['tree'],
                      parents=re.findall(_parent_hash_rx, matches['parents']),
                      author_name=matches['author_name'],
                      author_mail=matches['author_mail'],
                      author_sec=int(matches['asec']),
                      author_offset=parse_tz_offset(matches['atz']),
                      committer_name=matches['committer_name'],
                      committer_mail=matches['committer_mail'],
                      committer_sec=int(matches['csec']),
                      committer_offset=parse_tz_offset(matches['ctz']),
                      gpgsig=parse_commit_gpgsig(matches['gpgsig']),
                      message=matches['message'])


def get_cat_data(cat_iterator, expected_type):
    _, kind, _ = next(cat_iterator)
    if kind != expected_type:
        raise Exception('expected %r, saw %r' % (expected_type, kind))
    return b''.join(cat_iterator)

def get_commit_items(id, cp):
    return parse_commit(get_cat_data(cp.get(id), b'commit'))

def _local_git_date_str(epoch_sec):
    return b'%d %s' % (epoch_sec, utc_offset_str(epoch_sec))


def _git_date_str(epoch_sec, tz_offset_sec):
    offs =  tz_offset_sec // 60
    return b'%d %s%02d%02d' \
        % (epoch_sec,
           b'+' if offs >= 0 else b'-',
           abs(offs) // 60,
           abs(offs) % 60)


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
        assert s[0] != b'0'  # 0-padded octal is not acceptable in a git tree
        l.append(s)
    return b''.join(l)


def tree_decode(buf):
    """Generate a list of (mode,name,hash) from the git tree object in buf."""
    ofs = 0
    while ofs < len(buf):
        z = buf.find(b'\0', ofs)
        assert(z > ofs)
        spl = buf[ofs:z].split(b' ', 1)
        assert(len(spl) == 2)
        mode,name = spl
        sha = buf[z+1:z+1+20]
        ofs = z+1+20
        yield (int(mode, 8), name, sha)


def _encode_packobj(type, content, compression_level=1):
    if compression_level not in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9):
        raise ValueError('invalid compression level %s' % compression_level)
    szout = b''
    sz = len(content)
    szbits = (sz & 0x0f) | (_typemap[type]<<4)
    sz >>= 4
    while 1:
        if sz: szbits |= 0x80
        szout += bytes_from_uint(szbits)
        if not sz:
            break
        szbits = sz & 0x7f
        sz >>= 7
    z = zlib.compressobj(compression_level)
    yield szout
    yield z.compress(content)
    yield z.flush()


def _decode_packobj(buf):
    assert(buf)
    c = byte_int(buf[0])
    type = _typermap[(c & 0x70) >> 4]
    sz = c & 0x0f
    shift = 4
    i = 0
    while c & 0x80:
        i += 1
        c = byte_int(buf[i])
        sz |= (c & 0x7f) << shift
        shift += 7
        if not (c & 0x80):
            break
    return (type, zlib.decompress(buf[i+1:]))


class PackIdx(object):
    def find_offset(self, hash):
        """Get the offset of an object inside the index file."""
        idx = self._idx_from_hash(hash)
        if idx != None:
            return self._ofs_from_idx(idx)
        return None

    def exists(self, hash, want_source=False):
        """Return nonempty if the object exists in this index."""
        if hash and (self._idx_from_hash(hash) != None):
            return want_source and os.path.basename(self.name) or True
        return None

    def _idx_from_hash(self, hash):
        global _total_searches, _total_steps
        _total_searches += 1
        assert(len(hash) == 20)
        b1 = byte_int(hash[0])
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
        self.shatable = buffer(self.map, self.sha_ofs, self.nsha * 24)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        with pending_raise(value, rethrow=False):
            self.close()

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
        self.shatable = buffer(self.map, self.sha_ofs, self.nsha*20)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        with pending_raise(value, rethrow=False):
            self.close()

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
        # Q: was this also intended to prevent opening multiple repos?
        assert(_mpi_count == 0) # these things suck tons of VM; don't waste it
        _mpi_count += 1
        self.open = True
        self.dir = dir
        self.also = set()
        self.packs = []
        self.do_bloom = False
        self.bloom = None
        self.ignore_midx = ignore_midx
        try:
            self.refresh()
        except BaseException as ex:
            with pending_raise(ex):
                self.close()

    def close(self):
        global _mpi_count
        if not self.open:
            assert _mpi_count == 0
            return
        _mpi_count -= 1
        assert _mpi_count == 0
        self.also = None
        self.bloom, bloom = None, self.bloom
        self.packs, packs = None, self.packs
        self.open = False
        with ExitStack() as stack:
            for pack in packs:
                stack.enter_context(pack)
            if bloom:
                bloom.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        with pending_raise(value, rethrow=False):
            self.close()

    def __del__(self):
        assert not self.open

    def __iter__(self):
        return iter(idxmerge(self.packs))

    def __len__(self):
        return sum(len(pack) for pack in self.packs)

    def exists(self, hash, want_source=False):
        """Return nonempty if the object exists in the index files."""
        global _total_searches
        _total_searches += 1
        if hash in self.also:
            return True
        if self.do_bloom and self.bloom:
            if self.bloom.exists(hash):
                self.do_bloom = False
            else:
                _total_searches -= 1  # was counted by bloom
                return None
        for i in range(len(self.packs)):
            p = self.packs[i]
            _total_searches -= 1  # will be incremented by sub-pack
            ix = p.exists(hash, want_source=want_source)
            if ix:
                # reorder so most recently used packs are searched first
                self.packs = [p] + self.packs[:i] + self.packs[i+1:]
                return ix
        self.do_bloom = True
        return None

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
                with pending_raise(ex):
                    if self.bloom:
                        self.bloom.close()

        debug1('PackIdxList: using %d index%s.\n'
            % (len(self.packs), len(self.packs)!=1 and 'es' or ''))

    def add(self, hash):
        """Insert an additional object in the list."""
        self.also.add(hash)


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


def create_commit_blob(tree, parent,
                       author, adate_sec, adate_tz,
                       committer, cdate_sec, cdate_tz,
                       msg):
    if adate_tz is not None:
        adate_str = _git_date_str(adate_sec, adate_tz)
    else:
        adate_str = _local_git_date_str(adate_sec)
    if cdate_tz is not None:
        cdate_str = _git_date_str(cdate_sec, cdate_tz)
    else:
        cdate_str = _local_git_date_str(cdate_sec)
    l = []
    if tree: l.append(b'tree %s' % hexlify(tree))
    if parent: l.append(b'parent %s' % hexlify(parent))
    if author: l.append(b'author %s %s' % (author, adate_str))
    if committer: l.append(b'committer %s %s' % (committer, cdate_str))
    l.append(b'')
    l.append(msg)
    return b'\n'.join(l)

def _make_objcache():
    return PackIdxList(repo(b'objects/pack'))

# bup-gc assumes that it can disable all PackWriter activities
# (bloom/midx/cache) via the constructor and close() arguments.

class PackWriter(object):
    """Writes Git objects inside a pack file."""
    def __init__(self, objcache_maker=_make_objcache, compression_level=1,
                 run_midx=True, on_pack_finish=None,
                 max_pack_size=None, max_pack_objects=None, repo_dir=None):
        self.closed = False
        self.repo_dir = repo_dir or repo()
        self.file = None
        self.parentfd = None
        self.count = 0
        self.outbytes = 0
        self.tmpdir = None
        self.idx = None
        self.objcache_maker = objcache_maker
        self.objcache = None
        self.compression_level = compression_level
        self.run_midx=run_midx
        self.on_pack_finish = on_pack_finish
        if not max_pack_size:
            max_pack_size = git_config_get(b'pack.packSizeLimit',
                                           repo_dir=self.repo_dir,
                                           opttype='int')
            if not max_pack_size:
                # larger packs slow down pruning
                max_pack_size = 1000 * 1000 * 1000
        self.max_pack_size = max_pack_size
        # cache memory usage is about 83 bytes per object
        self.max_pack_objects = max_pack_objects if max_pack_objects \
                                else max(1, self.max_pack_size // 5000)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        with pending_raise(value, rethrow=False):
            self.close()

    def _open(self):
        if not self.file:
            with ExitStack() as err_stack:
                objdir = dir = os.path.join(self.repo_dir, b'objects')
                self.tmpdir = err_stack.enter_context(temp_dir(dir=objdir, prefix=b'pack-tmp-'))
                self.file = err_stack.enter_context(open(self.tmpdir + b'/pack', 'w+b'))
                self.parentfd = err_stack.enter_context(finalized(os.open(objdir, os.O_RDONLY),
                                                                  lambda x: os.close(x)))
                self.file.write(b'PACK\0\0\0\2\0\0\0\0')
                self.idx = PackIdxV2Writer()
                err_stack.pop_all()

    def _raw_write(self, datalist, sha):
        self._open()
        f = self.file
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
        self.outbytes += nw
        self.count += 1
        return nw, crc

    def _update_idx(self, sha, crc, size):
        assert(sha)
        if self.idx:
            self.idx.add(sha, crc, self.file.tell() - size)

    def _write(self, sha, type, content):
        if verbose:
            log('>')
        assert sha
        size, crc = self._raw_write(_encode_packobj(type, content,
                                                    self.compression_level),
                                    sha=sha)
        if self.outbytes >= self.max_pack_size \
           or self.count >= self.max_pack_objects:
            self.breakpoint()
        return sha

    def _require_objcache(self):
        if self.objcache is None and self.objcache_maker:
            self.objcache = self.objcache_maker()
        if self.objcache is None:
            raise GitError(
                    "PackWriter not opened or can't check exists w/o objcache")

    def exists(self, id, want_source=False):
        """Return non-empty if an object is found in the object cache."""
        self._require_objcache()
        return self.objcache.exists(id, want_source=want_source)

    def just_write(self, sha, type, content):
        """Write an object to the pack file without checking for duplication."""
        self._write(sha, type, content)
        # If nothing else, gc doesn't have/want an objcache
        if self.objcache is not None:
            self.objcache.add(sha)

    def maybe_write(self, type, content):
        """Write an object to the pack file if not present and return its id."""
        sha = calc_hash(type, content)
        if not self.exists(sha):
            self._require_objcache()
            self.just_write(sha, type, content)
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
        """Create a commit object in the pack.  The date_sec values must be
        epoch-seconds, and if a tz is None, the local timezone is assumed."""
        content = create_commit_blob(tree, parent,
                                     author, adate_sec, adate_tz,
                                     committer, cdate_sec, cdate_tz,
                                     msg)
        return self.maybe_write(b'commit', content)

    def _end(self, run_midx=True, abort=False):
        # Ignores run_midx during abort
        self.tmpdir, tmpdir = None, self.tmpdir
        self.parentfd, pfd, = None, self.parentfd
        self.file, f = None, self.file
        self.idx, idx = None, self.idx
        try:
            with nullcontext_if_not(self.objcache), \
                 finalized(pfd, lambda x: x is not None and os.close(x)), \
                 nullcontext_if_not(f):
                if abort or not f:
                    return None

                # update object count
                f.seek(8)
                cp = struct.pack('!i', self.count)
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
                fdatasync(f.fileno())
                f.close()

                idx.write(tmpdir + b'/idx', packbin)
                nameprefix = os.path.join(self.repo_dir,
                                          b'objects/pack/pack-' +  hexlify(packbin))
                os.rename(tmpdir + b'/pack', nameprefix + b'.pack')
                os.rename(tmpdir + b'/idx', nameprefix + b'.idx')
                os.fsync(pfd)
                if self.on_pack_finish:
                    self.on_pack_finish(nameprefix)
                if run_midx:
                    auto_midx(os.path.join(self.repo_dir, b'objects/pack'))
                return nameprefix
        finally:
            if tmpdir:
                rmtree(tmpdir)
            # Must be last -- some of the code above depends on it
            self.objcache = None

    def abort(self):
        """Remove the pack file from disk."""
        self.closed = True
        self._end(abort=True)

    def breakpoint(self):
        """Clear byte and object counts and return the last processed id."""
        id = self._end(self.run_midx)
        self.outbytes = self.count = 0
        return id

    def close(self, run_midx=True):
        """Close the pack file and move it to its definitive path."""
        self.closed = True
        return self._end(run_midx=run_midx)

    def __del__(self):
        assert self.closed


class PackIdxV2Writer:
    def __init__(self):
        self.idx = list(list() for i in range(256))
        self.count = 0

    def add(self, sha, crc, offs):
        assert(sha)
        self.count += 1
        self.idx[byte_int(sha[0])].append((sha, crc, offs))

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
            fdatasync(idx_f.fileno())
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
            fdatasync(idx_f.fileno())
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
        debug2("resolved from ref: commit = %s\n" % hexlify(head))
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
    p = subprocess.Popen([b'git', b'update-ref', refname,
                          hexlify(newval)] + oldarg,
                         env=_gitenv(repo_dir),
                         close_fds=True)
    _git_wait(b'git update-ref', p)


def delete_ref(refname, oldvalue=None):
    """Delete a repository reference (see git update-ref(1))."""
    assert refname.startswith(b'refs/')
    oldvalue = [] if not oldvalue else [oldvalue]
    p = subprocess.Popen([b'git', b'update-ref', b'-d', refname] + oldvalue,
                         env=_gitenv(),
                         close_fds=True)
    _git_wait('git update-ref', p)


def guess_repo():
    """Return the global repodir or BUP_DIR when either is set, or ~/.bup.
    Usually, if you are interacting with a bup repository, you would
    not be calling this function but using check_repo_or_die().

    """
    if repodir:
        return repodir
    repo = environ.get(b'BUP_DIR')
    if not repo:
        repo = os.path.expanduser(b'~/.bup')
    return repo


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
    p = subprocess.Popen([b'git', b'--bare', b'init'], stdout=sys.stderr,
                         env=_gitenv(),
                         close_fds=True)
    _git_wait('git init', p)
    # Force the index version configuration in order to ensure bup works
    # regardless of the version of the installed Git binary.
    p = subprocess.Popen([b'git', b'config', b'pack.indexVersion', '2'],
                         stdout=sys.stderr, env=_gitenv(), close_fds=True)
    _git_wait('git config', p)
    # Enable the reflog
    p = subprocess.Popen([b'git', b'config', b'core.logAllRefUpdates', b'true'],
                         stdout=sys.stderr, env=_gitenv(), close_fds=True)
    _git_wait('git config', p)


def check_repo_or_die(path=None):
    """Check to see if a bup repository probably exists, and abort if not."""
    global repodir
    repodir = path or guess_repo()
    top = repo()
    pst = stat_if_exists(top + b'/objects/pack')
    if pst and stat.S_ISDIR(pst.st_mode):
        return
    if not pst:
        top_st = stat_if_exists(top)
        if not top_st:
            log('error: repository %r does not exist (see "bup help init")\n'
                % top)
            sys.exit(15)
    log('error: %s is not a repository\n' % path_msg(top))
    sys.exit(14)


def is_suitable_git(ver_str):
    if not ver_str.startswith(b'git version '):
        return 'unrecognized'
    ver_str = ver_str[len(b'git version '):]
    if ver_str.startswith(b'0.'):
        return 'insufficient'
    if ver_str.startswith(b'1.'):
        if re.match(br'1\.[012345]rc', ver_str):
            return 'insufficient'
        if re.match(br'1\.[01234]\.', ver_str):
            return 'insufficient'
        if re.match(br'1\.5\.[012345]($|\.)', ver_str):
            return 'insufficient'
        if re.match(br'1\.5\.6-rc', ver_str):
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
        log('error: git version must be at least 1.5.6\n')
        sys.exit(1)
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
            with pending_raise(ex):
                self.close()

    def _join(self, oid, path):
        it = self.get(oid)
        _, typ, _ = next(it)
        if typ == b'blob':
            yield from it
        elif typ == b'tree':
            treefile = b''.join(it)
            for mode, name, sha in tree_decode(treefile):
                yield from self._join(hexlify(sha), path + [name])
        elif typ == b'commit':
            treeline = b''.join(it).split(b'\n')[0]
            assert treeline.startswith(b'tree ')
            yield from self._join(treeline[5:], path + [f'commit:{oid!r}'])
        elif typ is None:
            path += [repr(oid)]
            raise GitError(f'missing ref at {path!r}')
        else:
            raise GitError(f'ref {oid!r} type {typ!r} is not blob/tree/commit')

    def join(self, id):
        """Generate a list of the content of all blobs that can be reached
        from an object.  The hash given in 'id' must point to a blob, a tree
        or a commit. The content of all blobs that can be seen from trees or
        commits will be added to the list.
        """
        yield from self._join(id, [])


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
    def __init__(self, oid):
        self.oid = oid
        KeyError.__init__(self, 'object %r is missing' % hexlify(oid))


class WalkItem:
    # The path is the mangled path, and if an item represents a fragment
    # of a chunked file, the chunk_path will be the chunked subtree path
    # for the chunk, i.e. ['', '2d3115e', ...].  The top-level path for a
    # chunked file will have a chunk_path of [''].  So some chunk subtree
    # of the file '/foo/bar/baz' might look like this:
    #
    #   item.path = ['foo', 'bar', 'baz.bup']
    #   item.chunk_path = ['', '2d3115e', '016b097']
    #   item.type = 'tree'
    #   ...
    __slots__ = 'oid', 'type', 'mode', 'path', 'chunk_path', 'data'
    def __init__(self, *, oid, type, mode, path, chunk_path, data):
        self.oid = oid
        self.type = type
        self.mode = mode
        self.path = path
        self.chunk_path = chunk_path
        self.data = data

def walk_object(get_ref, oidx, *, stop_at=None, include_data=None,
                oid_exists=None):
    """Yield everything reachable from oidx via get_ref (which must
    behave like CatPipe get) as a WalkItem, stopping whenever
    stop_at(oidx) returns logically true.  Set the data field to False
    when the object is missing, or None if the object exists but
    include_data is logically false.  Missing blobs may not be noticed
    unless include_data is logically true or oid_exists(oid) is
    provided.  Yield items depth first, post-order, i.e. parents after
    children.  A tree will be yielded (later) if stop_item(oidx) is
    false when it is first encountered.

    """

    # Maintain the pending stack on the heap to avoid stack overflow
    pending = [(oidx, [], [], None, None)]
    while len(pending):
        if isinstance(pending[-1], WalkItem):
            yield pending.pop()
            continue

        oidx, parent_path, chunk_path, mode, exp_typ = pending.pop()
        if stop_at and stop_at(oidx):
            continue

        oid = unhexlify(oidx)

        if (not include_data) and mode and exp_typ == b'blob':
            # If the object is a "regular file", then it's a leaf in
            # the graph, so we can skip reading the data if the caller
            # hasn't requested it.
            yield WalkItem(oid=oid, type=b'blob',
                           chunk_path=chunk_path, path=parent_path,
                           mode=mode,
                           data=bool(oid_exists(oid)) if oid_exists else None)
            continue

        item_it = get_ref(oidx)
        get_oidx, typ, _ = next(item_it)
        if not get_oidx:
            yield WalkItem(oid=unhexlify(oidx), type=exp_typ,
                           chunk_path=chunk_path, path=parent_path,
                           mode=mode, data=False)
            continue
        if typ not in (b'blob', b'commit', b'tree'):
            raise Exception('unexpected repository object type %r' % typ)
        if exp_typ and typ != exp_typ:
            raise Exception(f'{oidx.decode("ascii")} object type {typ} != {exp_typ}')

        # FIXME: set the mode based on the type when the mode is None
        if typ == b'blob' and not include_data:
            # Dump data until we can ask cat_pipe not to fetch it
            for ignored in item_it:
                pass
            data = None
        else:
            data = b''.join(item_it)

        item = WalkItem(oid=oid, type=typ,
                        chunk_path=chunk_path, path=parent_path,
                        mode=mode,
                        data=(data if include_data else None))

        if typ == b'blob':
            yield item
        elif typ == b'commit':
            pending.append(item)
            commit_items = parse_commit(data)
            # For now, all paths are rooted at the "nearest" commit
            for pid in commit_items.parents:
                pending.append((pid, [], [], mode, b'commit'))
            pending.append((commit_items.tree, [oidx], [],
                            hashsplit.GIT_MODE_TREE, b'tree'))
        elif typ == b'tree':
            pending.append(item)
            for mode, name, ent_id in tree_decode(data):
                demangled, bup_type = demangle_name(name, mode)
                if chunk_path:
                    sub_path = parent_path
                    sub_chunk_path = chunk_path + [name]
                else:
                    sub_path = parent_path + [name]
                    if bup_type == BUP_CHUNKED:
                        sub_chunk_path = [b'']
                    else:
                        sub_chunk_path = chunk_path
                pending.append((hexlify(ent_id), sub_path, sub_chunk_path,
                                mode,
                                b'tree' if stat.S_ISDIR(mode) else b'blob'))
