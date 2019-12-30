"""Virtual File System interface to bup repository content.

This module provides a path-based interface to the content of a bup
repository.

The VFS is structured like this:

  /SAVE-NAME/latest/...
  /SAVE-NAME/SAVE-DATE/...
  /.tag/TAG-NAME/...

Each path is represented by an item that has least an item.meta which
may be either a Metadata object, or an integer mode.  Functions like
item_mode() and item_size() will return the mode and size in either
case.  Any item.meta Metadata instances must not be modified directly.
Make a copy to modify via item.meta.copy() if needed, or call
copy_item().

The want_meta argument is advisory for calls that accept it, and it
may not be honored.  Callers must be able to handle an item.meta value
that is either an instance of Metadata or an integer mode, perhaps
via item_mode() or augment_item_meta().

Setting want_meta=False is rarely desirable since it can limit the VFS
to only the metadata that git itself can represent, and so for
example, fifos and sockets will appear to be regular files
(e.g. S_ISREG(item_mode(item)) will be true).  But the option is still
provided because it may be more efficient when just the path names or
the more limited metadata is sufficient.

Any given metadata object's size may be None, in which case the size
can be computed via item_size() or augment_item_meta(...,
include_size=True).

When traversing a directory using functions like contents(), the meta
value for any directories other than '.' will be a default directory
mode, not a Metadata object.  This is because the actual metadata for
a directory is stored inside the directory (see
fill_in_metadata_if_dir() or ensure_item_has_metadata()).

Commit items represent commits (e.g. /.tag/some-commit or
/foo/latest), and for most purposes, they appear as the underlying
tree.  S_ISDIR(item_mode(item)) will return true for both tree Items
and Commits and the commit's oid is the tree hash; the commit hash is
item.coid.

"""

from __future__ import absolute_import, print_function
from binascii import hexlify, unhexlify
from collections import namedtuple
from errno import EINVAL, ELOOP, ENOENT, ENOTDIR
from itertools import chain, dropwhile, groupby, tee
from random import randrange
from stat import S_IFDIR, S_IFLNK, S_IFREG, S_ISDIR, S_ISLNK, S_ISREG
from time import localtime, strftime
import re, sys

from bup import git, metadata, vint
from bup.compat import hexstr, range
from bup.git import BUP_CHUNKED, cp, get_commit_items, parse_commit, tree_decode
from bup.helpers import debug2, last
from bup.io import path_msg
from bup.metadata import Metadata
from bup.vint import read_bvec, write_bvec
from bup.vint import read_vint, write_vint
from bup.vint import read_vuint, write_vuint

if sys.version_info[0] < 3:
    from exceptions import IOError as py_IOError
else:
    py_IOError = IOError

# We currently assume that it's always appropriate to just forward IOErrors
# to a remote client.

class IOError(py_IOError):
    def __init__(self, errno, message, terminus=None):
        py_IOError.__init__(self, errno, message)
        self.terminus = terminus

def write_ioerror(port, ex):
    assert isinstance(ex, IOError)
    write_vuint(port,
                (1 if ex.errno is not None else 0)
                | (2 if ex.strerror is not None else 0)
                | (4 if ex.terminus is not None else 0))
    if ex.errno is not None:
        write_vint(port, ex.errno)
    if str(ex.strerror is not None):
        write_bvec(port, ex.strerror.encode('utf-8'))
    if ex.terminus is not None:
        write_resolution(port, ex.terminus)

def read_ioerror(port):
    mask = read_vuint(port)
    no = read_vint(port) if 1 & mask else None
    msg = read_bvec(port).decode('utf-8') if 2 & mask else None
    term = read_resolution(port) if 4 & mask else None
    return IOError(errno=no, message=msg, terminus=term)


default_file_mode = S_IFREG | 0o644
default_dir_mode = S_IFDIR | 0o755
default_symlink_mode = S_IFLNK | 0o755

def _default_mode_for_gitmode(gitmode):
    if S_ISREG(gitmode):
        return default_file_mode
    if S_ISDIR(gitmode):
        return default_dir_mode
    if S_ISLNK(gitmode):
        return default_symlink_mode
    raise Exception('unexpected git mode ' + oct(gitmode))

def _normal_or_chunked_file_size(repo, oid):
    """Return the size of the normal or chunked file indicated by oid."""
    # FIXME: --batch-format CatPipe?
    it = repo.cat(hexlify(oid))
    _, obj_t, size = next(it)
    ofs = 0
    while obj_t == b'tree':
        mode, name, last_oid = last(tree_decode(b''.join(it)))
        ofs += int(name, 16)
        it = repo.cat(hexlify(last_oid))
        _, obj_t, size = next(it)
    return ofs + sum(len(b) for b in it)

def _skip_chunks_before_offset(tree, offset):
    prev_ent = next(tree, None)
    if not prev_ent:
        return tree
    ent = None
    for ent in tree:
        ent_ofs = int(ent[1], 16)
        if ent_ofs > offset:
            return chain([prev_ent, ent], tree)
        if ent_ofs == offset:
            return chain([ent], tree)
        prev_ent = ent
    return [prev_ent]

def _tree_chunks(repo, tree, startofs):
    "Tree should be a sequence of (name, mode, hash) as per tree_decode()."
    assert(startofs >= 0)
    # name is the chunk's hex offset in the original file
    for mode, name, oid in _skip_chunks_before_offset(tree, startofs):
        ofs = int(name, 16)
        skipmore = startofs - ofs
        if skipmore < 0:
            skipmore = 0
        it = repo.cat(hexlify(oid))
        _, obj_t, size = next(it)
        data = b''.join(it)
        if S_ISDIR(mode):
            assert obj_t == b'tree'
            for b in _tree_chunks(repo, tree_decode(data), skipmore):
                yield b
        else:
            assert obj_t == b'blob'
            yield data[skipmore:]

class _ChunkReader:
    def __init__(self, repo, oid, startofs):
        it = repo.cat(hexlify(oid))
        _, obj_t, size = next(it)
        isdir = obj_t == b'tree'
        data = b''.join(it)
        if isdir:
            self.it = _tree_chunks(repo, tree_decode(data), startofs)
            self.blob = None
        else:
            self.it = None
            self.blob = data[startofs:]
        self.ofs = startofs

    def next(self, size):
        out = b''
        while len(out) < size:
            if self.it and not self.blob:
                try:
                    self.blob = next(self.it)
                except StopIteration:
                    self.it = None
            if self.blob:
                want = size - len(out)
                out += self.blob[:want]
                self.blob = self.blob[want:]
            if not self.it:
                break
        debug2('next(%d) returned %d\n' % (size, len(out)))
        self.ofs += len(out)
        return out

class _FileReader(object):
    def __init__(self, repo, oid, known_size=None):
        assert len(oid) == 20
        self.oid = oid
        self.ofs = 0
        self.reader = None
        self._repo = repo
        self._size = known_size

    def _compute_size(self):
        if not self._size:
            self._size = _normal_or_chunked_file_size(self._repo, self.oid)
        return self._size
        
    def seek(self, ofs):
        if ofs < 0 or ofs > self._compute_size():
            raise IOError(EINVAL, 'Invalid seek offset: %d' % ofs)
        self.ofs = ofs

    def tell(self):
        return self.ofs

    def read(self, count=-1):
        size = self._compute_size()
        if self.ofs >= size:
            return b''
        if count < 0:
            count = size - self.ofs
        if not self.reader or self.reader.ofs != self.ofs:
            self.reader = _ChunkReader(self._repo, self.oid, self.ofs)
        try:
            buf = self.reader.next(count)
        except:
            self.reader = None
            raise  # our offsets will be all screwed up otherwise
        self.ofs += len(buf)
        return buf

    def close(self):
        pass

    def __enter__(self):
        return self
    def __exit__(self, type, value, traceback):
        self.close()
        return False

_multiple_slashes_rx = re.compile(br'//+')

def _decompose_path(path):
    """Return a boolean indicating whether the path is absolute, and a
    reversed list of path elements, omitting any occurrences of "."
    and ignoring any leading or trailing slash.  If the path is
    effectively '/' or '.', return an empty list.

    """
    path = re.sub(_multiple_slashes_rx, b'/', path)
    if path == b'/':
        return True, True, []
    is_absolute = must_be_dir = False
    if path.startswith(b'/'):
        is_absolute = True
        path = path[1:]
    for suffix in (b'/', b'/.'):
        if path.endswith(suffix):
            must_be_dir = True
            path = path[:-len(suffix)]
    parts = [x for x in path.split(b'/') if x != b'.']
    parts.reverse()
    if not parts:
        must_be_dir = True  # e.g. path was effectively '.' or '/', etc.
    return is_absolute, must_be_dir, parts
    

Item = namedtuple('Item', ('meta', 'oid'))
Chunky = namedtuple('Chunky', ('meta', 'oid'))
FakeLink = namedtuple('FakeLink', ('meta', 'target'))
Root = namedtuple('Root', ('meta'))
Tags = namedtuple('Tags', ('meta'))
RevList = namedtuple('RevList', ('meta', 'oid'))
Commit = namedtuple('Commit', ('meta', 'oid', 'coid'))

item_types = frozenset((Item, Chunky, Root, Tags, RevList, Commit))
real_tree_types = frozenset((Item, Commit))

def write_item(port, item):
    kind = type(item)
    name = bytes(kind.__name__.encode('ascii'))
    meta = item.meta
    has_meta = 1 if isinstance(meta, Metadata) else 0
    if kind in (Item, Chunky, RevList):
        assert len(item.oid) == 20
        if has_meta:
            vint.send(port, 'sVs', name, has_meta, item.oid)
            Metadata.write(meta, port, include_path=False)
        else:
            vint.send(port, 'sVsV', name, has_meta, item.oid, item.meta)
    elif kind in (Root, Tags):
        if has_meta:
            vint.send(port, 'sV', name, has_meta)
            Metadata.write(meta, port, include_path=False)
        else:
            vint.send(port, 'sVV', name, has_meta, item.meta)
    elif kind == Commit:
        assert len(item.oid) == 20
        assert len(item.coid) == 20
        if has_meta:
            vint.send(port, 'sVss', name, has_meta, item.oid, item.coid)
            Metadata.write(meta, port, include_path=False)
        else:
            vint.send(port, 'sVssV', name, has_meta, item.oid, item.coid,
                      item.meta)
    elif kind == FakeLink:
        if has_meta:
            vint.send(port, 'sVs', name, has_meta, item.target)
            Metadata.write(meta, port, include_path=False)
        else:
            vint.send(port, 'sVsV', name, has_meta, item.target, item.meta)
    else:
        assert False

def read_item(port):
    def read_m(port, has_meta):
        if has_meta:
            m = Metadata.read(port)
            return m
        return read_vuint(port)
    kind, has_meta = vint.recv(port, 'sV')
    if kind == b'Item':
        oid, meta = read_bvec(port), read_m(port, has_meta)
        return Item(oid=oid, meta=meta)
    if kind == b'Chunky':
        oid, meta = read_bvec(port), read_m(port, has_meta)
        return Chunky(oid=oid, meta=meta)
    if kind == b'RevList':
        oid, meta = read_bvec(port), read_m(port, has_meta)
        return RevList(oid=oid, meta=meta)
    if kind == b'Root':
        return Root(meta=read_m(port, has_meta))
    if kind == b'Tags':
        return Tags(meta=read_m(port, has_meta))
    if kind == b'Commit':
        oid, coid = vint.recv(port, 'ss')
        meta = read_m(port, has_meta)
        return Commit(oid=oid, coid=coid, meta=meta)
    if kind == b'FakeLink':
        target, meta = read_bvec(port), read_m(port, has_meta)
        return FakeLink(target=target, meta=meta)
    assert False

def write_resolution(port, resolution):
    write_vuint(port, len(resolution))
    for name, item in resolution:
        write_bvec(port, name)
        if item:
            port.write(b'\x01')
            write_item(port, item)
        else:
            port.write(b'\x00')

def read_resolution(port):
    n = read_vuint(port)
    result = []
    for i in range(n):
        name = read_bvec(port)
        have_item = ord(port.read(1))
        assert have_item in (0, 1)
        item = read_item(port) if have_item else None
        result.append((name, item))
    return tuple(result)


_root = Root(meta=default_dir_mode)
_tags = Tags(meta=default_dir_mode)


### vfs cache

### A general purpose shared cache with (currently) cheap random
### eviction.  At the moment there is no weighting so a single commit
### item is just as likely to be evicted as an entire "rev-list".  See
### is_valid_cache_key for a description of the expected content.

_cache = {}
_cache_keys = []
_cache_max_items = 30000

def clear_cache():
    global _cache, _cache_keys
    _cache = {}
    _cache_keys = []

def is_valid_cache_key(x):
    """Return logically true if x looks like it could be a valid cache key
    (with respect to structure).  Current valid cache entries:
      res:... -> resolution
      itm:OID -> Commit
      rvl:OID -> {'.', commit, '2012...', next_commit, ...}
    """
    # Suspect we may eventually add "(container_oid, name) -> ...", and others.
    x_t = type(x)
    if x_t is bytes:
        tag = x[:4]
        if tag in (b'itm:', b'rvl:') and len(x) == 24:
            return True
        if tag == b'res:':
            return True

def cache_get(key):
    global _cache
    if not is_valid_cache_key(key):
        raise Exception('invalid cache key: ' + repr(key))
    return _cache.get(key)

def cache_notice(key, value):
    global _cache, _cache_keys, _cache_max_items
    if not is_valid_cache_key(key):
        raise Exception('invalid cache key: ' + repr(key))
    if key in _cache:
        return
    if len(_cache) < _cache_max_items:
        _cache_keys.append(key)
        _cache[key] = value
        return
    victim_i = randrange(0, len(_cache_keys))
    victim = _cache_keys[victim_i]
    del _cache[victim]
    _cache_keys[victim_i] = key
    _cache[key] = value

def cache_get_commit_item(oid, need_meta=True):
    """Return the requested tree item if it can be found in the cache.
    When need_meta is true don't return a cached item that only has a
    mode."""
    # tree might be stored independently, or as '.' with its entries.
    commit_key = b'itm:' + oid
    item = cache_get(commit_key)
    if item:
        if not need_meta:
            return item
        if isinstance(item.meta, Metadata):
            return item
    entries = cache_get(b'rvl:' + oid)
    if entries:
        return entries[b'.']

def cache_get_revlist_item(oid, need_meta=True):
    commit = cache_get_commit_item(oid, need_meta=need_meta)
    if commit:
        return RevList(oid=oid, meta=commit.meta)

def copy_item(item):
    """Return a completely independent copy of item, such that
    modifications will not affect the original.

    """
    meta = getattr(item, 'meta', None)
    if isinstance(meta, Metadata):
        return(item._replace(meta=meta.copy()))
    return item

def item_mode(item):
    """Return the integer mode (stat st_mode) for item."""
    m = item.meta
    if isinstance(m, Metadata):
        return m.mode
    return m

def _read_dir_meta(bupm):
    # This is because save writes unmodified Metadata() entries for
    # fake parents -- test-save-strip-graft.sh demonstrates.
    m = Metadata.read(bupm)
    if not m:
        return default_dir_mode
    assert m.mode is not None
    if m.size is None:
        m.size = 0
    return m

def tree_data_and_bupm(repo, oid):
    """Return (tree_bytes, bupm_oid) where bupm_oid will be None if the
    tree has no metadata (i.e. older bup save, or non-bup tree).

    """    
    assert len(oid) == 20
    it = repo.cat(hexlify(oid))
    _, item_t, size = next(it)
    data = b''.join(it)
    if item_t == b'commit':
        commit = parse_commit(data)
        it = repo.cat(commit.tree)
        _, item_t, size = next(it)
        data = b''.join(it)
        assert item_t == b'tree'
    elif item_t != b'tree':
        raise Exception('%s is not a tree or commit' % hexstr(oid))
    for _, mangled_name, sub_oid in tree_decode(data):
        if mangled_name == b'.bupm':
            return data, sub_oid
        if mangled_name > b'.bupm':
            break
    return data, None

def _find_treeish_oid_metadata(repo, oid):
    """Return the metadata for the tree or commit oid, or None if the tree
    has no metadata (i.e. older bup save, or non-bup tree).

    """
    tree_data, bupm_oid = tree_data_and_bupm(repo, oid)
    if bupm_oid:
        with _FileReader(repo, bupm_oid) as meta_stream:
            return _read_dir_meta(meta_stream)
    return None

def _readlink(repo, oid):
    return b''.join(repo.join(hexlify(oid)))

def readlink(repo, item):
    """Return the link target of item, which must be a symlink.  Reads the
    target from the repository if necessary."""
    assert repo
    assert S_ISLNK(item_mode(item))
    if isinstance(item, FakeLink):
        return item.target
    if isinstance(item.meta, Metadata):
        target = item.meta.symlink_target
        if target:
            return target
    return _readlink(repo, item.oid)

def _compute_item_size(repo, item):
    mode = item_mode(item)
    if S_ISREG(mode):
        size = _normal_or_chunked_file_size(repo, item.oid)
        return size
    if S_ISLNK(mode):
        if isinstance(item, FakeLink):
            return len(item.target)
        return len(_readlink(repo, item.oid))
    return 0

def item_size(repo, item):
    """Return the size of item, computing it if necessary."""
    m = item.meta
    if isinstance(m, Metadata) and m.size is not None:
        return m.size
    return _compute_item_size(repo, item)

def tree_data_reader(repo, oid):
    """Return an open reader for all of the data contained within oid.  If
    oid refers to a tree, recursively concatenate all of its contents."""
    return _FileReader(repo, oid)

def fopen(repo, item):
    """Return an open reader for the given file item."""
    assert S_ISREG(item_mode(item))
    return tree_data_reader(repo, item.oid)

def _commit_item_from_data(oid, data):
    info = parse_commit(data)
    return Commit(meta=default_dir_mode,
                  oid=unhexlify(info.tree),
                  coid=oid)

def _commit_item_from_oid(repo, oid, require_meta):
    commit = cache_get_commit_item(oid, need_meta=require_meta)
    if commit and ((not require_meta) or isinstance(commit.meta, Metadata)):
        return commit
    it = repo.cat(hexlify(oid))
    _, typ, size = next(it)
    assert typ == b'commit'
    commit = _commit_item_from_data(oid, b''.join(it))
    if require_meta:
        meta = _find_treeish_oid_metadata(repo, commit.oid)
        if meta:
            commit = commit._replace(meta=meta)
    commit_key = b'itm:' + oid
    cache_notice(commit_key, commit)
    return commit

def _revlist_item_from_oid(repo, oid, require_meta):
    commit = _commit_item_from_oid(repo, oid, require_meta)
    return RevList(oid=oid, meta=commit.meta)

def root_items(repo, names=None, want_meta=True):
    """Yield (name, item) for the items in '/' in the VFS.  Return
    everything if names is logically false, otherwise return only
    items with a name in the collection.

    """
    # FIXME: what about non-leaf refs like 'refs/heads/foo/bar/baz?

    global _root, _tags
    if not names:
        yield b'.', _root
        yield b'.tag', _tags
        # FIXME: maybe eventually support repo.clone() or something
        # and pass in two repos, so we can drop the tuple() and stream
        # in parallel (i.e. meta vs refs).
        for name, oid in tuple(repo.refs([], limit_to_heads=True)):
            assert(name.startswith(b'refs/heads/'))
            yield name[11:], _revlist_item_from_oid(repo, oid, want_meta)
        return

    if b'.' in names:
        yield b'.', _root
    if b'.tag' in names:
        yield b'.tag', _tags
    for ref in names:
        if ref in (b'.', b'.tag'):
            continue
        it = repo.cat(b'refs/heads/' + ref)
        oidx, typ, size = next(it)
        if not oidx:
            for _ in it: pass
            continue
        assert typ == b'commit'
        commit = parse_commit(b''.join(it))
        yield ref, _revlist_item_from_oid(repo, unhexlify(oidx), want_meta)

def ordered_tree_entries(tree_data, bupm=None):
    """Yields (name, mangled_name, kind, gitmode, oid) for each item in
    tree, sorted by name.

    """
    # Sadly, the .bupm entries currently aren't in git tree order,
    # i.e. they don't account for the fact that git sorts trees
    # (including our chunked trees) as if their names ended with "/",
    # so "fo" sorts after "fo." iff fo is a directory.  This makes
    # streaming impossible when we need the metadata.
    def result_from_tree_entry(tree_entry):
        gitmode, mangled_name, oid = tree_entry
        name, kind = git.demangle_name(mangled_name, gitmode)
        return name, mangled_name, kind, gitmode, oid

    tree_ents = (result_from_tree_entry(x) for x in tree_decode(tree_data))
    if bupm:
        tree_ents = sorted(tree_ents, key=lambda x: x[0])
    for ent in tree_ents:
        yield ent
    
def tree_items(oid, tree_data, names=frozenset(), bupm=None):

    def tree_item(ent_oid, kind, gitmode):
        if kind == BUP_CHUNKED:
            meta = Metadata.read(bupm) if bupm else default_file_mode
            return Chunky(oid=ent_oid, meta=meta)

        if S_ISDIR(gitmode):
            # No metadata here (accessable via '.' inside ent_oid).
            return Item(meta=default_dir_mode, oid=ent_oid)

        return Item(oid=ent_oid,
                    meta=(Metadata.read(bupm) if bupm \
                          else _default_mode_for_gitmode(gitmode)))

    assert len(oid) == 20
    if not names:
        dot_meta = _read_dir_meta(bupm) if bupm else default_dir_mode
        yield b'.', Item(oid=oid, meta=dot_meta)
        tree_entries = ordered_tree_entries(tree_data, bupm)
        for name, mangled_name, kind, gitmode, ent_oid in tree_entries:
            if mangled_name == b'.bupm':
                continue
            assert name != b'.'
            yield name, tree_item(ent_oid, kind, gitmode)
        return

    # Assumes the tree is properly formed, i.e. there are no
    # duplicates, and entries will be in git tree order.
    if type(names) not in (frozenset, set):
        names = frozenset(names)
    remaining = len(names)

    # Account for the bupm sort order issue (cf. ordered_tree_entries above)
    last_name = max(names) if bupm else max(names) + b'/'

    if b'.' in names:
        dot_meta = _read_dir_meta(bupm) if bupm else default_dir_mode
        yield b'.', Item(oid=oid, meta=dot_meta)
        if remaining == 1:
            return
        remaining -= 1

    tree_entries = ordered_tree_entries(tree_data, bupm)
    for name, mangled_name, kind, gitmode, ent_oid in tree_entries:
        if mangled_name == b'.bupm':
            continue
        assert name != b'.'
        if name not in names:
            if name > last_name:
                break  # given bupm sort order, we're finished
            if (kind == BUP_CHUNKED or not S_ISDIR(gitmode)) and bupm:
                Metadata.read(bupm)
            continue
        yield name, tree_item(ent_oid, kind, gitmode)
        if remaining == 1:
            break
        remaining -= 1

def tree_items_with_meta(repo, oid, tree_data, names):
    # For now, the .bupm order doesn't quite match git's, and we don't
    # load the tree data incrementally anyway, so we just work in RAM
    # via tree_data.
    assert len(oid) == 20
    bupm = None
    for _, mangled_name, sub_oid in tree_decode(tree_data):
        if mangled_name == b'.bupm':
            bupm = _FileReader(repo, sub_oid)
            break
        if mangled_name > b'.bupm':
            break
    for item in tree_items(oid, tree_data, names, bupm):
        yield item

_save_name_rx = re.compile(br'^\d\d\d\d-\d\d-\d\d-\d{6}(-\d+)?$')
        
def _reverse_suffix_duplicates(strs):
    """Yields the elements of strs, with any runs of duplicate values
    suffixed with -N suffixes, where the zero padded integer N
    decreases to 0 by 1 (e.g. 10, 09, ..., 00).

    """
    for name, duplicates in groupby(strs):
        ndup = len(tuple(duplicates))
        if ndup == 1:
            yield name
        else:
            ndig = len(str(ndup - 1))
            fmt = b'%s-' + b'%0' + (b'%d' % ndig) + b'd'
            for i in range(ndup - 1, -1, -1):
                yield fmt % (name, i)

def parse_rev(f):
    items = f.readline().split(None)
    assert len(items) == 2
    tree, auth_sec = items
    return unhexlify(tree), int(auth_sec)

def _name_for_rev(rev):
    commit_oidx, (tree_oid, utc) = rev
    return strftime('%Y-%m-%d-%H%M%S', localtime(utc)).encode('ascii')

def _item_for_rev(rev):
    commit_oidx, (tree_oid, utc) = rev
    coid = unhexlify(commit_oidx)
    item = cache_get_commit_item(coid, need_meta=False)
    if item:
        return item
    item = Commit(meta=default_dir_mode, oid=tree_oid, coid=coid)
    commit_key = b'itm:' + coid
    cache_notice(commit_key, item)
    return item

def cache_commit(repo, oid):
    """Build, cache, and return a "name -> commit_item" dict of the entire
    commit rev-list.

    """
    # For now, always cache with full metadata
    entries = {}
    entries[b'.'] = _revlist_item_from_oid(repo, oid, True)
    revs = repo.rev_list((hexlify(oid),), format=b'%T %at',
                         parse=parse_rev)
    rev_items, rev_names = tee(revs)
    revs = None  # Don't disturb the tees
    rev_names = _reverse_suffix_duplicates(_name_for_rev(x) for x in rev_names)
    rev_items = (_item_for_rev(x) for x in rev_items)
    tip = None
    for item in rev_items:
        name = next(rev_names)
        tip = tip or (name, item)
        entries[name] = item
    entries[b'latest'] = FakeLink(meta=default_symlink_mode, target=tip[0])
    revlist_key = b'rvl:' + tip[1].coid
    cache_notice(revlist_key, entries)
    return entries

def revlist_items(repo, oid, names):
    assert len(oid) == 20

    # Special case '.' instead of caching the whole history since it's
    # the only way to get the metadata for the commit.
    if names and all(x == b'.' for x in names):
        yield b'.', _revlist_item_from_oid(repo, oid, True)
        return

    # For now, don't worry about the possibility of the contents being
    # "too big" for the cache.
    revlist_key = b'rvl:' + oid
    entries = cache_get(revlist_key)
    if not entries:
        entries = cache_commit(repo, oid)

    if not names:
        for name in sorted(entries.keys()):
            yield name, entries[name]
        return

    names = frozenset(name for name in names
                      if _save_name_rx.match(name) or name in (b'.', b'latest'))

    if b'.' in names:
        yield b'.', entries[b'.']
    for name in (n for n in names if n != b'.'):
        commit = entries.get(name)
        if commit:
            yield name, commit

def tags_items(repo, names):
    global _tags

    def tag_item(oid):
        assert len(oid) == 20
        oidx = hexlify(oid)
        it = repo.cat(oidx)
        _, typ, size = next(it)
        if typ == b'commit':
            return cache_get_commit_item(oid, need_meta=False) \
                or _commit_item_from_data(oid, b''.join(it))
        for _ in it: pass
        if typ == b'blob':
            return Item(meta=default_file_mode, oid=oid)
        elif typ == b'tree':
            return Item(meta=default_dir_mode, oid=oid)
        raise Exception('unexpected tag type ' + typ.decode('ascii')
                        + ' for tag ' + path_msg(name))

    if not names:
        yield b'.', _tags
        # We have to pull these all into ram because tag_item calls cat()
        for name, oid in tuple(repo.refs(names, limit_to_tags=True)):
            assert(name.startswith(b'refs/tags/'))
            name = name[10:]
            yield name, tag_item(oid)
        return

    # Assumes no duplicate refs
    if type(names) not in (frozenset, set):
        names = frozenset(names)
    remaining = len(names)
    last_name = max(names)
    if b'.' in names:
        yield b'.', _tags
        if remaining == 1:
            return
        remaining -= 1

    for name, oid in repo.refs(names, limit_to_tags=True):
        assert(name.startswith(b'refs/tags/'))
        name = name[10:]
        if name > last_name:
            return
        if name not in names:
            continue
        yield name, tag_item(oid)
        if remaining == 1:
            return
        remaining -= 1

def contents(repo, item, names=None, want_meta=True):
    """Yields information about the items contained in item.  Yields
    (name, item) for each name in names, if the name exists, in an
    unspecified order.  If there are no names, then yields (name,
    item) for all items, including, a first item named '.'
    representing the container itself.

    The meta value for any directories other than '.' will be a
    default directory mode, not a Metadata object.  This is because
    the actual metadata for a directory is stored inside the directory
    (see fill_in_metadata_if_dir() or ensure_item_has_metadata()).

    Note that want_meta is advisory.  For any given item, item.meta
    might be a Metadata instance or a mode, and if the former,
    meta.size might be None.  Missing sizes can be computed via via
    item_size() or augment_item_meta(..., include_size=True).

    Do not modify any item.meta Metadata instances directly.  If
    needed, make a copy via item.meta.copy() and modify that instead.

    """
    # Q: are we comfortable promising '.' first when no names?
    global _root, _tags
    assert repo
    assert S_ISDIR(item_mode(item))
    item_t = type(item)
    if item_t in real_tree_types:
        it = repo.cat(hexlify(item.oid))
        _, obj_t, size = next(it)
        data = b''.join(it)
        if obj_t != b'tree':
            for _ in it: pass
            # Note: it shouldn't be possible to see an Item with type
            # 'commit' since a 'commit' should always produce a Commit.
            raise Exception('unexpected git ' + obj_t.decode('ascii'))
        if want_meta:
            item_gen = tree_items_with_meta(repo, item.oid, data, names)
        else:
            item_gen = tree_items(item.oid, data, names)
    elif item_t == RevList:
        item_gen = revlist_items(repo, item.oid, names)
    elif item_t == Root:
        item_gen = root_items(repo, names, want_meta)
    elif item_t == Tags:
        item_gen = tags_items(repo, names)
    else:
        raise Exception('unexpected VFS item ' + str(item))
    for x in item_gen:
        yield x

def _resolve_path(repo, path, parent=None, want_meta=True, follow=True):
    cache_key = b'res:%d%d%d:%s\0%s' \
                % (bool(want_meta), bool(follow), repo.id(),
                   (b'/'.join(x[0] for x in parent) if parent else b''),
                   path)
    resolution = cache_get(cache_key)
    if resolution:
        return resolution

    def notice_resolution(r):
        cache_notice(cache_key, r)
        return r

    def raise_dir_required_but_not_dir(path, parent, past):
        raise IOError(ENOTDIR,
                      "path %s%s resolves to non-directory %r"
                      % (path,
                         ' (relative to %r)' % parent if parent else '',
                         past),
                      terminus=past)
    global _root
    assert repo
    assert len(path)
    if parent:
        for x in parent:
            assert len(x) == 2
            assert type(x[0]) in (bytes, str)
            assert type(x[1]) in item_types
        assert parent[0][1] == _root
        if not S_ISDIR(item_mode(parent[-1][1])):
            raise IOError(ENOTDIR,
                          'path resolution parent %r is not a directory'
                          % (parent,))
    is_absolute, must_be_dir, future = _decompose_path(path)
    if must_be_dir:
        follow = True
    if not future:  # path was effectively '.' or '/'
        if is_absolute:
            return notice_resolution(((b'', _root),))
        if parent:
            return notice_resolution(tuple(parent))
        return notice_resolution(((b'', _root),))
    if is_absolute:
        past = [(b'', _root)]
    else:
        past = list(parent) if parent else [(b'', _root)]
    hops = 0
    while True:
        if not future:
            if must_be_dir and not S_ISDIR(item_mode(past[-1][1])):
                raise_dir_required_but_not_dir(path, parent, past)
            return notice_resolution(tuple(past))
        segment = future.pop()
        if segment == b'..':
            assert len(past) > 0
            if len(past) > 1:  # .. from / is /
                assert S_ISDIR(item_mode(past[-1][1]))
                past.pop()
        else:
            parent_name, parent_item = past[-1]
            wanted = (segment,) if not want_meta else (b'.', segment)
            items = tuple(contents(repo, parent_item, names=wanted,
                                   want_meta=want_meta))
            if not want_meta:
                item = items[0][1] if items else None
            else:  # First item will be '.' and have the metadata
                item = items[1][1] if len(items) == 2 else None
                dot, dot_item = items[0]
                assert dot == b'.'
                past[-1] = parent_name, parent_item
            if not item:
                past.append((segment, None),)
                return notice_resolution(tuple(past))
            mode = item_mode(item)
            if not S_ISLNK(mode):
                if not S_ISDIR(mode):
                    past.append((segment, item),)
                    if future:
                        raise IOError(ENOTDIR,
                                      'path %r%s ends internally in non-directory here: %r'
                                      % (path,
                                         ' (relative to %r)' % parent if parent else '',
                                         past),
                                      terminus=past)
                    if must_be_dir:
                        raise_dir_required_but_not_dir(path, parent, past)
                    return notice_resolution(tuple(past))
                # It's treeish
                if want_meta and type(item) in real_tree_types:
                    dir_meta = _find_treeish_oid_metadata(repo, item.oid)
                    if dir_meta:
                        item = item._replace(meta=dir_meta)
                past.append((segment, item))
            else:  # symlink
                if not future and not follow:
                    past.append((segment, item),)
                    continue
                if hops > 100:
                    raise IOError(ELOOP,
                                  'too many symlinks encountered while resolving %r%s'
                                  % (path, ' relative to %r' % parent if parent else ''),
                                  terminus=tuple(past + [(segment, item)]))
                target = readlink(repo, item)
                is_absolute, _, target_future = _decompose_path(target)
                if is_absolute:
                    if not target_future:  # path was effectively '/'
                        return notice_resolution(((b'', _root),))
                    past = [(b'', _root)]
                    future = target_future
                else:
                    future.extend(target_future)
                hops += 1
                
def resolve(repo, path, parent=None, want_meta=True, follow=True):
    """Follow the path in the virtual filesystem and return a tuple
    representing the location, if any, denoted by the path.  Each
    element in the result tuple will be (name, info), where info will
    be a VFS item that can be passed to functions like item_mode().

    If follow is false, and if the final path element is a symbolic
    link, don't follow it, just return it in the result.

    If a path segment that does not exist is encountered during
    resolution, the result will represent the location of the missing
    item, and that item in the result will be None.

    Any attempt to traverse a non-directory will raise a VFS ENOTDIR
    IOError exception.

    Any symlinks along the path, including at the end, will be
    resolved.  A VFS IOError with the errno attribute set to ELOOP
    will be raised if too many symlinks are traversed while following
    the path.  That exception is effectively like a normal
    ELOOP IOError exception, but will include a terminus element
    describing the location of the failure, which will be a tuple of
    (name, info) elements.

    The parent, if specified, must be a sequence of (name, item)
    tuples, and will provide the starting point for the resolution of
    the path.  If no parent is specified, resolution will start at
    '/'.

    The result may include elements of parent directly, so they must
    not be modified later.  If this is a concern, pass in "name,
    copy_item(item) for name, item in parent" instead.

    When want_meta is true, detailed metadata will be included in each
    result item if it's avaiable, otherwise item.meta will be an
    integer mode.  The metadata size may or may not be provided, but
    can be computed by item_size() or augment_item_meta(...,
    include_size=True).  Setting want_meta=False is rarely desirable
    since it can limit the VFS to just the metadata git itself can
    represent, and so, as an example, fifos and sockets will appear to
    be regular files (e.g. S_ISREG(item_mode(item)) will be true) .
    But the option is provided because it may be more efficient when
    only the path names or the more limited metadata is sufficient.

    Do not modify any item.meta Metadata instances directly.  If
    needed, make a copy via item.meta.copy() and modify that instead.

    """
    if repo.is_remote():
        # Redirect to the more efficient remote version
        return repo.resolve(path, parent=parent, want_meta=want_meta,
                            follow=follow)
    result = _resolve_path(repo, path, parent=parent, want_meta=want_meta,
                           follow=follow)
    _, leaf_item = result[-1]
    if leaf_item and follow:
        assert not S_ISLNK(item_mode(leaf_item))
    return result

def try_resolve(repo, path, parent=None, want_meta=True):
    """If path does not refer to a symlink, does not exist, or refers to a
    valid symlink, behave exactly like resolve(..., follow=True).  If
    path refers to an invalid symlink, behave like resolve(...,
    follow=False).

    """
    res = resolve(repo, path, parent=parent, want_meta=want_meta, follow=False)
    leaf_name, leaf_item = res[-1]
    if not leaf_item:
        return res
    if not S_ISLNK(item_mode(leaf_item)):
        return res
    follow = resolve(repo, leaf_name, parent=res[:-1], want_meta=want_meta)
    follow_name, follow_item = follow[-1]
    if follow_item:
        return follow
    return res

def augment_item_meta(repo, item, include_size=False):
    """Ensure item has a Metadata instance for item.meta.  If item.meta is
    currently a mode, replace it with a compatible "fake" Metadata
    instance.  If include_size is true, ensure item.meta.size is
    correct, computing it if needed.  If item.meta is a Metadata
    instance, this call may modify it in place or replace it.

    """
    # If we actually had parallelism, we'd need locking...
    assert repo
    m = item.meta
    if isinstance(m, Metadata):
        if include_size and m.size is None:
            m.size = _compute_item_size(repo, item)
            return item._replace(meta=m)
        return item
    # m is mode
    meta = Metadata()
    meta.mode = m
    meta.uid = meta.gid = meta.atime = meta.mtime = meta.ctime = 0
    if S_ISLNK(m):
        if isinstance(item, FakeLink):
            target = item.target
        else:
            target = _readlink(repo, item.oid)
        meta.symlink_target = target
        meta.size = len(target)
    elif include_size:
        meta.size = _compute_item_size(repo, item)
    return item._replace(meta=meta)

def fill_in_metadata_if_dir(repo, item):
    """If item is a directory and item.meta is not a Metadata instance,
    attempt to find the metadata for the directory.  If found, return
    a new item augmented to include that metadata.  Otherwise, return
    item.  May be useful for the output of contents().

    """
    if S_ISDIR(item_mode(item)) and not isinstance(item.meta, Metadata):
        items = tuple(contents(repo, item, (b'.',), want_meta=True))
        assert len(items) == 1
        assert items[0][0] == b'.'
        item = items[0][1]
    return item

def ensure_item_has_metadata(repo, item, include_size=False):
    """If item is a directory, attempt to find and add its metadata.  If
    the item still doesn't have a Metadata instance for item.meta,
    give it one via augment_item_meta().  May be useful for the output
    of contents().

    """
    return augment_item_meta(repo,
                             fill_in_metadata_if_dir(repo, item),
                             include_size=include_size)
