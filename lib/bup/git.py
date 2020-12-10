"""Git interaction library.
bup repositories are in Git format. This library allows us to
interact with the Git data structures.
"""

from __future__ import absolute_import, print_function
import errno, os, sys, zlib, time, subprocess, struct, stat, re, tempfile, glob
from array import array
from binascii import hexlify, unhexlify
from collections import namedtuple
from itertools import islice
from numbers import Integral

from bup import _helpers, compat, hashsplit, path, midx, bloom, xstat
from bup.compat import (buffer,
                        byte_int, bytes_from_byte, bytes_from_uint,
                        environ,
                        items,
                        range,
                        reraise)
from bup.io import path_msg
from bup.helpers import (Sha1, add_error, chunkyreader, debug1, debug2,
                         exo,
                         fdatasync,
                         hostname, localtime, log,
                         merge_dict,
                         merge_iter,
                         mmap_read, mmap_readwrite,
                         parse_num,
                         progress, qprogress, stat_if_exists,
                         unlink,
                         utc_offset_str)
from bup.pwdgrp import username, userfullname


verbose = 0
repodir = None  # The default repository, once initialized

_typemap =  {b'blob': 3, b'tree': 2, b'commit': 1, b'tag': 4}
_typermap = {v: k for k, v in items(_typemap)}


_total_searches = 0
_total_steps = 0


class GitError(Exception):
    pass


def _gitenv(repo_dir=None):
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

def git_config_get(option, repo_dir=None):
    cmd = (b'git', b'config', b'--get', option)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                         env=_gitenv(repo_dir=repo_dir),
                         close_fds=True)
    r = p.stdout.read()
    rc = p.wait()
    if rc == 0:
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


# FIXME: derived from http://git.rsbx.net/Documents/Git_Data_Formats.txt
# Make sure that's authoritative.
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


def all_packdirs():
    paths = [repo(b'objects/pack')]
    paths += glob.glob(repo(b'index-cache/*/.'))
    return paths


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
    else:
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


def _encode_looseobj(type, content, compression_level=1):
    z = zlib.compressobj(compression_level)
    yield z.compress(b'%s %d\0' % (type, len(content)))
    yield z.compress(content)
    yield z.flush()


def _decode_looseobj(buf):
    assert(buf);
    s = zlib.decompress(buf)
    i = s.find(b'\0')
    assert(i > 0)
    l = s[:i].split(b' ')
    type = l[0]
    sz = int(l[1])
    content = s[i+1:]
    assert(type in _typemap)
    assert(sz == len(content))
    return (type, content)


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


class PackIdx:
    def __init__(self):
        assert(0)

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

    def close(self):
        if self.map is not None:
            self.shatable = None
            self.map.close()
            self.map = None


class PackIdxV2(PackIdx):
    """Object representation of a Git pack index (version 2) file."""
    def __init__(self, filename, f):
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
        self.close()

    def __len__(self):
        return int(self.nsha)  # int() from long for python 2

    def _ofs_from_idx(self, idx):
        if idx >= self.nsha or idx < 0:
            raise IndexError('invalid pack index index %d' % idx)
        ofs_ofs = self.ofstable_ofs + idx * 4
        ofs = struct.unpack_from('!I', self.map, offset=ofs_ofs)[0]
        if ofs & 0x80000000:
            idx64 = ofs & 0x7fffffff
            ofs64_ofs = self.ofs64table_ofs + idx64 * 8
            ofs = struct.unpack_from('!Q', self.map, offset=ofs64_ofs)[0]
        return ofs

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
        if self.map is not None:
            self.shatable = None
            self.map.close()
            self.map = None


_mpi_count = 0
class PackIdxList:
    def __init__(self, dir, ignore_midx=False):
        global _mpi_count
        assert(_mpi_count == 0) # these things suck tons of VM; don't waste it
        _mpi_count += 1
        self.dir = dir
        self.also = set()
        self.packs = []
        self.do_bloom = False
        self.bloom = None
        self.ignore_midx = ignore_midx
        self.refresh()

    def __del__(self):
        global _mpi_count
        _mpi_count -= 1
        assert(_mpi_count == 0)

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
                        mx = midx.PackMidx(full)
                        (mxd, mxf) = os.path.split(mx.name)
                        broken = False
                        for n in mx.idxnames:
                            if not os.path.exists(os.path.join(mxd, n)):
                                log(('warning: index %s missing\n'
                                     '  used by %s\n')
                                    % (path_msg(n), path_msg(mxf)))
                                broken = True
                        if broken:
                            mx.close()
                            del mx
                            unlink(full)
                        else:
                            midxl.append(mx)
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
                    elif not ix.force_keep:
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
            if self.bloom is None and os.path.exists(bfull):
                self.bloom = bloom.ShaBloom(bfull)
            self.packs = list(set(d.values()))
            self.packs.sort(reverse=True, key=lambda x: len(x))
            if self.bloom and self.bloom.valid() and len(self.bloom) >= len(self):
                self.do_bloom = True
            else:
                self.bloom = None
        debug1('PackIdxList: using %d index%s.\n'
            % (len(self.packs), len(self.packs)!=1 and 'es' or ''))

    def add(self, hash):
        """Insert an additional object in the list."""
        self.also.add(hash)


def open_idx(filename):
    if filename.endswith(b'.idx'):
        f = open(filename, 'rb')
        header = f.read(8)
        if header[0:4] == b'\377tOc':
            version = struct.unpack('!I', header[4:8])[0]
            if version == 2:
                return PackIdxV2(filename, f)
            else:
                raise GitError('%s: expected idx file version 2, got %d'
                               % (path_msg(filename), version))
        elif len(header) == 8 and header[0:4] < b'\377tOc':
            return PackIdxV1(filename, f)
        else:
            raise GitError('%s: unrecognized idx file header'
                           % path_msg(filename))
    elif filename.endswith(b'.midx'):
        return midx.PackMidx(filename)
    else:
        raise GitError('idx filenames must end with .idx or .midx')


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


def _make_objcache():
    return PackIdxList(repo(b'objects/pack'))

# bup-gc assumes that it can disable all PackWriter activities
# (bloom/midx/cache) via the constructor and close() arguments.

class PackWriter:
    """Writes Git objects inside a pack file."""
    def __init__(self, objcache_maker=_make_objcache, compression_level=1,
                 run_midx=True, on_pack_finish=None,
                 max_pack_size=None, max_pack_objects=None, repo_dir=None):
        self.repo_dir = repo_dir or repo()
        self.file = None
        self.parentfd = None
        self.count = 0
        self.outbytes = 0
        self.filename = None
        self.idx = None
        self.objcache_maker = objcache_maker
        self.objcache = None
        self.compression_level = compression_level
        self.run_midx=run_midx
        self.on_pack_finish = on_pack_finish
        if not max_pack_size:
            max_pack_size = git_config_get(b'pack.packSizeLimit',
                                           repo_dir=self.repo_dir)
            if max_pack_size is not None:
                max_pack_size = parse_num(max_pack_size)
            if not max_pack_size:
                # larger packs slow down pruning
                max_pack_size = 1000 * 1000 * 1000
        self.max_pack_size = max_pack_size
        # cache memory usage is about 83 bytes per object
        self.max_pack_objects = max_pack_objects if max_pack_objects \
                                else max(1, self.max_pack_size // 5000)

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def _open(self):
        if not self.file:
            objdir = dir = os.path.join(self.repo_dir, b'objects')
            fd, name = tempfile.mkstemp(suffix=b'.pack', dir=objdir)
            try:
                self.file = os.fdopen(fd, 'w+b')
            except:
                os.close(fd)
                raise
            try:
                self.parentfd = os.open(objdir, os.O_RDONLY)
            except:
                f = self.file
                self.file = None
                f.close()
                raise
            assert name.endswith(b'.pack')
            self.filename = name[:-5]
            self.file.write(b'PACK\0\0\0\2\0\0\0\0')
            self.idx = PackIdxV2Writer()

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
            reraise(GitError(e))
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
        if not sha:
            sha = calc_hash(type, content)
        size, crc = self._raw_write(_encode_packobj(type, content,
                                                    self.compression_level),
                                    sha=sha)
        if self.outbytes >= self.max_pack_size \
           or self.count >= self.max_pack_objects:
            self.breakpoint()
        return sha

    def breakpoint(self):
        """Clear byte and object counts and return the last processed id."""
        id = self._end(self.run_midx)
        self.outbytes = self.count = 0
        return id

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
        return self.maybe_write(b'commit', b'\n'.join(l))

    def abort(self):
        """Remove the pack file from disk."""
        f = self.file
        if f:
            pfd = self.parentfd
            self.file = None
            self.parentfd = None
            self.idx = None
            try:
                try:
                    os.unlink(self.filename + b'.pack')
                finally:
                    f.close()
            finally:
                if pfd is not None:
                    os.close(pfd)

    def _end(self, run_midx=True):
        f = self.file
        if not f: return None
        self.file = None
        try:
            self.objcache = None
            idx = self.idx
            self.idx = None

            # update object count
            f.seek(8)
            cp = struct.pack('!i', self.count)
            assert(len(cp) == 4)
            f.write(cp)

            # calculate the pack sha1sum
            f.seek(0)
            sum = Sha1()
            for b in chunkyreader(f):
                sum.update(b)
            packbin = sum.digest()
            f.write(packbin)
            fdatasync(f.fileno())
        finally:
            f.close()

        obj_list_sha = idx.write(self.filename + b'.idx', packbin)
        nameprefix = os.path.join(self.repo_dir,
                                  b'objects/pack/pack-' +  obj_list_sha)
        if os.path.exists(self.filename + b'.map'):
            os.unlink(self.filename + b'.map')
        os.rename(self.filename + b'.pack', nameprefix + b'.pack')
        os.rename(self.filename + b'.idx', nameprefix + b'.idx')
        try:
            os.fsync(self.parentfd)
        finally:
            os.close(self.parentfd)

        if run_midx:
            auto_midx(os.path.join(self.repo_dir, b'objects/pack'))

        if self.on_pack_finish:
            self.on_pack_finish(nameprefix)

        return nameprefix

    def close(self, run_midx=True):
        """Close the pack file and move it to its definitive path."""
        return self._end(run_midx=run_midx)


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

            obj_list_sum = Sha1()
            for b in chunkyreader(idx_f, 20 * self.count):
                idx_sum.update(b)
                obj_list_sum.update(b)
            namebase = hexlify(obj_list_sum.digest())

            for b in chunkyreader(idx_f):
                idx_sum.update(b)
            idx_f.write(idx_sum.digest())
            fdatasync(idx_f.fileno())
            return namebase
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


def get_commit_dates(refs, repo_dir=None):
    """Get the dates for the specified commit refs.  For now, every unique
       string in refs must resolve to a different commit or this
       function will fail."""
    result = []
    for ref in refs:
        commit = get_commit_items(ref, cp(repo_dir))
        result.append(commit.author_sec)
    return result


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

    pL = PackIdxList(repo(b'objects/pack', repo_dir=repo_dir))

    if len(committish) == 40:
        try:
            hash = unhexlify(committish)
        except TypeError:
            return None

        if pL.exists(hash):
            return hash

    return None


def update_ref(refname, newval, oldval, repo_dir=None):
    """Update a repository reference."""
    if not oldval:
        oldval = b''
    assert refname.startswith(b'refs/heads/') \
        or refname.startswith(b'refs/tags/')
    p = subprocess.Popen([b'git', b'update-ref', refname,
                          hexlify(newval), hexlify(oldval)],
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


def guess_repo(path=None):
    """Set the path value in the global variable "repodir".
    This makes bup look for an existing bup repository, but not fail if a
    repository doesn't exist. Usually, if you are interacting with a bup
    repository, you would not be calling this function but using
    check_repo_or_die().
    """
    global repodir
    if path:
        repodir = path
    if not repodir:
        repodir = environ.get(b'BUP_DIR')
        if not repodir:
            repodir = os.path.expanduser(b'~/.bup')


def init_repo(path=None):
    """Create the Git bare repository for bup in a given path."""
    guess_repo(path)
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
    guess_repo(path)
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


class _AbortableIter:
    def __init__(self, it, onabort = None):
        self.it = it
        self.onabort = onabort
        self.done = None

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self.it)
        except StopIteration as e:
            self.done = True
            raise
        except:
            self.abort()
            raise

    next = __next__

    def abort(self):
        """Abort iteration and call the abortion callback, if needed."""
        if not self.done:
            self.done = True
            if self.onabort:
                self.onabort()

    def __del__(self):
        self.abort()


class CatPipe:
    """Link to 'git cat-file' that is used to retrieve blob data."""
    def __init__(self, repo_dir = None):
        require_suitable_git()
        self.repo_dir = repo_dir
        self.p = self.inprogress = None

    def _abort(self):
        if self.p:
            self.p.stdout.close()
            self.p.stdin.close()
        self.p = None
        self.inprogress = None

    def restart(self):
        self._abort()
        self.p = subprocess.Popen([b'git', b'cat-file', b'--batch'],
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  close_fds = True,
                                  bufsize = 4096,
                                  env=_gitenv(self.repo_dir))

    def get(self, ref):
        """Yield (oidx, type, size), followed by the data referred to by ref.
        If ref does not exist, only yield (None, None, None).

        """
        if not self.p or self.p.poll() != None:
            self.restart()
        assert(self.p)
        poll_result = self.p.poll()
        assert(poll_result == None)
        if self.inprogress:
            log('get: opening %r while %r is open\n' % (ref, self.inprogress))
        assert(not self.inprogress)
        assert ref.find(b'\n') < 0
        assert ref.find(b'\r') < 0
        assert not ref.startswith(b'-')
        self.inprogress = ref
        self.p.stdin.write(ref + b'\n')
        self.p.stdin.flush()
        hdr = self.p.stdout.readline()
        if hdr.endswith(b' missing\n'):
            self.inprogress = None
            yield None, None, None
            return
        info = hdr.split(b' ')
        if len(info) != 3 or len(info[0]) != 40:
            raise GitError('expected object (id, type, size), got %r' % info)
        oidx, typ, size = info
        size = int(size)
        it = _AbortableIter(chunkyreader(self.p.stdout, size),
                            onabort=self._abort)
        try:
            yield oidx, typ, size
            for blob in it:
                yield blob
            readline_result = self.p.stdout.readline()
            assert readline_result == b'\n'
            self.inprogress = None
        except Exception as e:
            it.abort()
            raise

    def _join(self, it):
        _, typ, _ = next(it)
        if typ == b'blob':
            for blob in it:
                yield blob
        elif typ == b'tree':
            treefile = b''.join(it)
            for (mode, name, sha) in tree_decode(treefile):
                for blob in self.join(hexlify(sha)):
                    yield blob
        elif typ == b'commit':
            treeline = b''.join(it).split(b'\n')[0]
            assert treeline.startswith(b'tree ')
            for blob in self.join(treeline[5:]):
                yield blob
        else:
            raise GitError('invalid object type %r: expected blob/tree/commit'
                           % typ)

    def join(self, id):
        """Generate a list of the content of all blobs that can be reached
        from an object.  The hash given in 'id' must point to a blob, a tree
        or a commit. The content of all blobs that can be seen from trees or
        commits will be added to the list.
        """
        for d in self._join(self.get(id)):
            yield d


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


WalkItem = namedtuple('WalkItem', ['oid', 'type', 'mode',
                                   'path', 'chunk_path', 'data'])
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


def walk_object(get_ref, oidx, stop_at=None, include_data=None):
    """Yield everything reachable from oidx via get_ref (which must behave
    like CatPipe get) as a WalkItem, stopping whenever stop_at(oidx)
    returns true.  Throw MissingObject if a hash encountered is
    missing from the repository, and don't read or return blob content
    in the data field unless include_data is set.

    """
    # Maintain the pending stack on the heap to avoid stack overflow
    pending = [(oidx, [], [], None)]
    while len(pending):
        oidx, parent_path, chunk_path, mode = pending.pop()
        oid = unhexlify(oidx)
        if stop_at and stop_at(oidx):
            continue

        if (not include_data) and mode and stat.S_ISREG(mode):
            # If the object is a "regular file", then it's a leaf in
            # the graph, so we can skip reading the data if the caller
            # hasn't requested it.
            yield WalkItem(oid=oid, type=b'blob',
                           chunk_path=chunk_path, path=parent_path,
                           mode=mode,
                           data=None)
            continue

        item_it = get_ref(oidx)
        get_oidx, typ, _ = next(item_it)
        if not get_oidx:
            raise MissingObject(unhexlify(oidx))
        if typ not in (b'blob', b'commit', b'tree'):
            raise Exception('unexpected repository object type %r' % typ)

        # FIXME: set the mode based on the type when the mode is None
        if typ == b'blob' and not include_data:
            # Dump data until we can ask cat_pipe not to fetch it
            for ignored in item_it:
                pass
            data = None
        else:
            data = b''.join(item_it)

        yield WalkItem(oid=oid, type=typ,
                       chunk_path=chunk_path, path=parent_path,
                       mode=mode,
                       data=(data if include_data else None))

        if typ == b'commit':
            commit_items = parse_commit(data)
            for pid in commit_items.parents:
                pending.append((pid, parent_path, chunk_path, mode))
            pending.append((commit_items.tree, parent_path, chunk_path,
                            hashsplit.GIT_MODE_TREE))
        elif typ == b'tree':
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
                                mode))
