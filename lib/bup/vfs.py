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

from binascii import hexlify, unhexlify
from collections import namedtuple
from errno import EINVAL, ELOOP, ENOTDIR
from itertools import tee
from random import randrange
from stat import S_IFDIR, S_IFLNK, S_IFREG, S_ISDIR, S_ISLNK, S_ISREG
from time import localtime, strftime
import re

from bup import git
from bup.git import \
    (BUP_CHUNKED,
     MissingObject,
     GitError,
     find_tree_entry,
     last_tree_entry,
     parse_commit,
     tree_entries,
     tree_iter)
from bup.helpers import debug2
from bup.io import path_msg
from bup.metadata import Metadata

py_IOError = IOError

# We currently assume that it's always appropriate to just forward IOErrors
# to a remote client.

class IOError(py_IOError):
    def __init__(self, errno, message, terminus=None):
        py_IOError.__init__(self, errno, message)
        self.terminus = terminus

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

def get_ref(repo, ref):
    """Yield (oidx, type, size, data_iter) for ref.

    If ref is missing, yield (None, None, None, None).

    """
    it = repo.cat(ref)
    found_oidx, obj_t, size = next(it)
    if not found_oidx:
        return None, None, None, None
    return found_oidx, obj_t, size, it

def get_oidx(repo, oidx, *, throw_missing=True):
    """Yield (oidx, type, size, data_iter) for oidx.

    If oidx is missing, raise a MissingObject if throw_missing is
    false, otherwise yield (None, None, None, None).

    """
    assert len(oidx) == 40
    result = get_ref(repo, oidx)
    if not result[0] and throw_missing:
        raise MissingObject(unhexlify(oidx))
    return result

def _normal_or_chunked_file_size(repo, oid):
    """Return the size of the normal or chunked file indicated by oid."""
    # FIXME: --batch-format CatPipe?
    _, obj_t, _, it = get_oidx(repo, hexlify(oid))
    ofs = 0
    while obj_t == b'tree':
        mode, name, last_oid = last_tree_entry(b''.join(it))
        ofs += int(name, 16)
        _, obj_t, _, it = get_oidx(repo, hexlify(last_oid))
    return ofs + sum(len(b) for b in it)

def _skip_chunks_before_offset(tree_data, offset):
    entries = tree_entries(tree_data)
    for i in range(len(entries)):
        ent_ofs = int(entries[i][1], 16)
        if ent_ofs > offset:
            return entries[i - 1:]
        if ent_ofs == offset:
            return entries[i:]
    return entries[-1:]

def _tree_chunks(repo, tree_data, startofs):
    assert(startofs >= 0)
    # name is the chunk's hex offset in the original file
    for mode, name, oid in _skip_chunks_before_offset(tree_data, startofs):
        ofs = int(name, 16)
        skipmore = startofs - ofs
        if skipmore < 0:
            skipmore = 0
        _, obj_t, _, it = get_oidx(repo, hexlify(oid))
        data = b''.join(it)
        if S_ISDIR(mode):
            assert obj_t == b'tree'
            yield from _tree_chunks(repo, data, skipmore)
        else:
            assert obj_t == b'blob'
            yield data[skipmore:]

class _ChunkReader:
    def __init__(self, repo, oid, startofs):
        _, obj_t, _, it = get_oidx(repo, hexlify(oid))
        isdir = obj_t == b'tree'
        data = b''.join(it)
        if isdir:
            self.it = _tree_chunks(repo, data, startofs)
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

class _FileReader:
    def __init__(self, repo, oid, known_size=None):
        assert len(oid) == 20
        self.closed = False
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
        self.closed = True

    def __enter__(self): return self
    def __exit__(self, type, value, traceback): self.close()
    def __del__(self): assert self.closed

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

item_types = (Item, Chunky, Root, Tags, RevList, Commit)
real_tree_types = (Item, Commit)


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
    if isinstance(x, bytes):
        tag = x[:4]
        if tag in (b'itm:', b'rvl:') and len(x) == 24:
            return True
        if tag == b'res:':
            return True
    return False

def cache_get(key):
    global _cache
    if not is_valid_cache_key(key):
        raise Exception('invalid cache key: ' + repr(key))
    return _cache.get(key)

def cache_notice(key, value, overwrite=False):
    global _cache, _cache_keys, _cache_max_items
    if not is_valid_cache_key(key):
        raise Exception('invalid cache key: ' + repr(key))
    if key in _cache:
        if overwrite:
            _cache[key] = value
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

def _has_metadata_if_needed(item, need_meta):
    if not need_meta:
        return True
    if isinstance(item.meta, Metadata):
        return True
    return False

def cache_get_commit_item(oid, need_meta=True):
    """Return the requested tree item if it can be found in the cache.
    When need_meta is true don't return a cached item that only has a
    mode."""
    # tree might be stored independently, or as '.' with its entries.
    commit_key = b'itm:' + oid
    item = cache_get(commit_key)
    if item:
        if _has_metadata_if_needed(item, need_meta):
            return item
    entries = cache_get(b'rvl:' + oid)
    if entries:
        item = entries[b'.']
        if _has_metadata_if_needed(item, need_meta):
            return item
    return None

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
    return m

def _treeish_tree_data(repo, oid):
    assert len(oid) == 20
    _, item_t, _, it = get_oidx(repo, hexlify(oid))
    data = b''.join(it)
    if item_t == b'commit':
        commit = parse_commit(data)
        _, item_t, _, it = get_oidx(repo, commit.tree)
        data = b''.join(it)
        assert item_t == b'tree'
    elif item_t != b'tree':
        raise Exception('%s is not a tree or commit' % oid.hex())
    return data

def tree_data_and_bupm(repo, oid):
    """Return (tree_bytes, bupm_oid) where bupm_oid will be None if the
    tree has no metadata (i.e. older bup save, or non-bup tree).

    """
    data = _treeish_tree_data(repo, oid)
    for _, mangled_name, sub_oid in tree_entries(data):
        if mangled_name == b'.bupm':
            return data, sub_oid
        if mangled_name > b'.bupm':
            break
    return data, None

def _find_treeish_oid_metadata(repo, oid):
    """Return the metadata for the tree or commit oid, or None if the tree
    has no metadata (i.e. older bup save, or non-bup tree).

    """
    bupm_ent = find_tree_entry(b'.bupm', _treeish_tree_data(repo, oid))
    if bupm_ent:
        with _FileReader(repo, bupm_ent[2]) as meta_stream:
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
    if S_ISDIR(mode):
        return None
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
    _, typ, _, it = get_oidx(repo, hexlify(oid))
    assert typ == b'commit'
    commit = _commit_item_from_data(oid, b''.join(it))
    if require_meta:
        meta = _find_treeish_oid_metadata(repo, commit.oid)
        if meta:
            commit = commit._replace(meta=meta)
    commit_key = b'itm:' + oid
    cache_notice(commit_key, commit, overwrite=True)
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
            continue
        assert typ == b'commit'
        commit = parse_commit(b''.join(it))
        yield ref, _revlist_item_from_oid(repo, unhexlify(oidx), want_meta)

def ordered_tree_entries(entries, bupm=None):
    """Returns [(name, mangled_name, kind, gitmode, oid) ...] for each
    item in tree, sorted by name.

    """
    # Sadly, the .bupm entries currently aren't in git tree order,
    # but in unmangled name order. They _do_ account for the fact
    # that git sorts trees (including chunked trees) as if their
    # names ended with "/" (so "fo" sorts after "fo." iff fo is a
    # directory), but we apply this on the unmangled names in save
    # rather than on the mangled names.
    # This makes streaming impossible when we need the metadata.
    def result_from_tree_entry(tree_entry):
        gitmode, mangled_name, oid = tree_entry
        name, kind = git.demangle_name(mangled_name, gitmode)
        return name, mangled_name, kind, gitmode, oid

    tree_ents = [result_from_tree_entry(x) for x in entries]
    if bupm:
        tree_ents.sort(key=lambda x: x[0])
    return tree_ents


def _tree_items_except_dot(oid, entries, names=None, bupm=None):
    """Returns all tree items except ".", and assumes that any bupm is
    positioned just after that entry."""

    def tree_item(ent_oid, kind, gitmode):
        if kind == BUP_CHUNKED:
            meta = Metadata.read(bupm) if bupm else default_file_mode
            return Chunky(oid=ent_oid, meta=meta)

        if S_ISDIR(gitmode):
            # No metadata here (accessable via '.' inside ent_oid).
            return Item(meta=default_dir_mode, oid=ent_oid)

        meta = Metadata.read(bupm) if bupm else None
        # handle the case of metadata being empty/missing in bupm
        # (or there not being bupm at all)
        if meta is None:
            meta = _default_mode_for_gitmode(gitmode)
        return Item(oid=ent_oid, meta=meta)

    tree_ents = ordered_tree_entries(entries, bupm)

    assert isinstance(names, (set, frozenset)) or names is None
    assert len(oid) == 20
    if not names:
        for name, mangled_name, kind, gitmode, ent_oid in tree_ents:
            if mangled_name == b'.bupm':
                continue
            assert name != b'.'
            yield name, tree_item(ent_oid, kind, gitmode)
        return

    remaining = len(names)
    if b'.' in names:
        if remaining == 1:
            return
        remaining -= 1

    # Account for the bupm sort order issue (cf. ordered_tree_entries above)
    last_name = max(names) if bupm else max(names) + b'/'

    for name, mangled_name, kind, gitmode, ent_oid in tree_ents:
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

def _get_tree_object(repo, oid):
    _, kind, _, res = get_oidx(repo, hexlify(oid))
    assert kind == b'tree', f'expected oid {oid.hex()} to be tree, not {kind!r}'
    return b''.join(res)

def _find_bupm_oid(entries):
    for _, mangled_name, sub_oid in entries:
        if mangled_name == b'.bupm':
            return sub_oid
            break
        if mangled_name > b'.bupm':
            break
    return None

def _split_subtree_items(repo, level, oid, entries, names, want_meta, root=True):
    """Traverse the "internal" nodes of a split tree, yielding all of
    the real items (at the leaves).

    """
    assert len(oid) == 20
    assert isinstance(level, int)
    assert level >= 0
    if level == 0:
        bupm_oid = _find_bupm_oid(entries) if want_meta else None
        if not bupm_oid:
            yield from _tree_items_except_dot(oid, entries, names)
        else:
            with _FileReader(repo, bupm_oid) as bupm:
                Metadata.read(bupm) # skip dummy entry provided for older bups
                yield from _tree_items_except_dot(oid, entries, names, bupm)
    else:
        for _, mangled_name, sub_oid in entries:
            if root:
                if mangled_name == b'.bupm':
                    continue
                if mangled_name.endswith(b'.bupd'):
                    continue
            assert not mangled_name.endswith(b'.bup'), \
                f'found {path_msg(mangled_name)} in split subtree'
            if not mangled_name.endswith(b'.bupl'):
                assert mangled_name[-5:-1] != b'.bup', \
                    f'found {path_msg(mangled_name)} in split subtree'
            yield from _split_subtree_items(repo, level - 1, sub_oid,
                                            tree_entries(_get_tree_object(repo, sub_oid)),
                                            names, want_meta, False)

_tree_depth_rx = re.compile(br'\.bupd\.([0-9]+)(?:\..*)?\.bupd')

def _parse_tree_depth(mangled_name):
    """Return the tree DEPTH from a mangled_name like
    .bupd.DEPTH.bupd, but leave open the possibility of future
    .bupd.DEPTH.*.bupd extensions.

    """
    m = _tree_depth_rx.fullmatch(mangled_name)
    if not m:
        raise Exception(f'Could not parse split tree depth in {mangled_name}')
    depth = int(m.group(1))
    assert depth > 0
    return depth

def tree_items(repo, oid, tree_data, names, *, want_meta=True):
    # For now, the .bupm order doesn't quite match git's, and we don't
    # load the tree data incrementally anyway, so we just work in RAM
    # via tree_data.
    assert len(oid) == 20

    # Assumes the tree is properly formed, i.e. there are no
    # duplicates, and entries will be in git tree order.
    if names is not None and not isinstance(names, (frozenset, set)):
        names = frozenset(names)
    dot_requested = not names or b'.' in names

    entries = tree_entries(tree_data)
    depth = None
    bupm_oid = None
    for _, mangled_name, sub_oid in entries:
        if mangled_name.endswith(b'.bupd'):
            depth = _parse_tree_depth(mangled_name)
            if not dot_requested: # all other metadata in "leaf" .bupm files
                break
        if mangled_name == b'.bupm':
            bupm_oid = sub_oid
            break
        if mangled_name > b'.bupm':
            break

    if want_meta and bupm_oid:
        if depth is None:
            with _FileReader(repo, bupm_oid) as bupm:
                if not dot_requested: # skip it
                    Metadata.read(bupm)
                else:
                    yield b'.', Item(oid=oid, meta=_read_dir_meta(bupm))
                yield from _tree_items_except_dot(oid, entries, names, bupm)
        else:
            if dot_requested:
                with _FileReader(repo, bupm_oid) as bupm:
                    yield b'.', Item(oid=oid, meta=_read_dir_meta(bupm))
            yield from _split_subtree_items(repo, depth, oid, entries, names, True)
        return

    if dot_requested:
        yield b'.', Item(oid=oid, meta=default_dir_mode)
    if not depth:
        yield from _tree_items_except_dot(oid, entries, names)
    else:
        yield from _split_subtree_items(repo, depth, oid, entries, names, False)

_save_name_rx = re.compile(br'^\d\d\d\d-\d\d-\d\d-\d{6}(-\d+)?$')

def _reverse_suffix_duplicates(strs):
    """Yields the elements of strs, with any duplicate values
    suffixed with -N suffixes, where the zero padded integer N
    decreases to 0 by 1 (e.g. 10, 09, ..., 00).

    """
    seen = {}
    strs = list(strs)
    for name in strs:
        if name in seen:
            seen[name][0] += 1
            seen[name][1] += 1
        else:
            seen[name] = [1, 1]
    for name in strs:
        curdup, ndup = seen[name]
        if ndup == 1:
            yield name
        else:
            ndig = len(str(ndup - 1))
            fmt = b'%s-' + b'%0' + (b'%d' % ndig) + b'd'
            yield fmt % (name, curdup - 1)
        seen[name][0] -= 1
    del seen

def save_names_for_commit_utcs(utcs):
    names = (strftime('%Y-%m-%d-%H%M%S', localtime(utc)).encode('ascii')
             for utc in utcs)
    return _reverse_suffix_duplicates(names)

def parse_rev(f):
    items = f.readline().split(None)
    assert len(items) == 2
    tree, auth_sec = items
    return unhexlify(tree), int(auth_sec)

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

# non-string singleton
_HAS_META_ENTRY = object()

def cache_commit(repo, oid, require_meta=True):
    """Build, cache, and return a "name -> commit_item" dict of the entire
    commit rev-list.

    """
    entries = {}
    entries[b'.'] = _revlist_item_from_oid(repo, oid, require_meta)
    revs = repo.rev_list((hexlify(oid),), format=b'%T %at',
                         parse=parse_rev)
    rev_items, rev_names = tee(revs)
    revs = None  # Don't disturb the tees
    rev_names = save_names_for_commit_utcs(x[1][1] for x in rev_names)
    rev_items = (_item_for_rev(x) for x in rev_items)
    tip = None
    for name, item in zip(rev_names, rev_items):
        tip = tip or (name, item)
        assert not name in entries
        entries[name] = item
    entries[b'latest'] = FakeLink(meta=default_symlink_mode, target=tip[0])
    revlist_key = b'rvl:' + tip[1].coid
    entries[_HAS_META_ENTRY] = require_meta
    cache_notice(revlist_key, entries, overwrite=True)
    return entries

def revlist_items(repo, oid, names, require_meta=True):
    assert len(oid) == 20

    # Special case '.' instead of caching the whole history since it's
    # the only way to get the metadata for the commit.
    if names and all(x == b'.' for x in names):
        yield b'.', _revlist_item_from_oid(repo, oid, require_meta)
        return

    # For now, don't worry about the possibility of the contents being
    # "too big" for the cache.
    revlist_key = b'rvl:' + oid
    entries = cache_get(revlist_key)
    if entries and require_meta and not entries[_HAS_META_ENTRY]:
        entries = None
    if not entries:
        entries = cache_commit(repo, oid, require_meta)

    if not names:
        for name in sorted((n for n in entries.keys() if n != _HAS_META_ENTRY)):
            yield name, entries[name]
        return

    names = frozenset(name for name in names
                      if _save_name_rx.match(name) or name in (b'.', b'latest'))

    if b'.' in names:
        yield b'.', entries[b'.']
    for name in (n for n in names if n != b'.'):
        if name == _HAS_META_ENTRY:
            continue
        commit = entries.get(name)
        if commit:
            yield name, commit

def tags_items(repo, names):
    global _tags

    def tag_item(oid):
        assert len(oid) == 20
        cached = cache_get_commit_item(oid, need_meta=False)
        if cached:
            return cached
        _, typ, _, it = get_oidx(repo, hexlify(oid))
        if typ == b'commit':
            return _commit_item_from_data(oid, b''.join(it))
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
    if not isinstance(names, (frozenset, set)):
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
    unspecified order. Items that don't exist are omitted.  If there
    are no names, then yields (name, item) for all items, including, a
    first item named '.' representing the container itself.

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
    if isinstance(item, real_tree_types):
        _, obj_t, _, it = get_oidx(repo, hexlify(item.oid))
        data = b''.join(it)
        if obj_t != b'tree':
            for _ in it: pass
            # Note: it shouldn't be possible to see an Item with type
            # 'commit' since a 'commit' should always produce a Commit.
            raise Exception('unexpected git ' + obj_t.decode('ascii'))
        yield from tree_items(repo, item.oid, data, names, want_meta=want_meta)
    elif isinstance(item, RevList):
        yield from revlist_items(repo, item.oid, names,
                                 require_meta=want_meta)
    elif isinstance(item, Root):
        yield from root_items(repo, names, want_meta)
    elif isinstance(item, Tags):
        yield from tags_items(repo, names)
    else:
        raise Exception('unexpected VFS item ' + str(item))

def _resolve_path(repo, path, parent=None, want_meta=True, follow=True):
    cache_key = b'res:%d%d%d:%s\0%s' \
                % (bool(want_meta), bool(follow), id(repo),
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
            assert isinstance(x[0], (bytes, str))
            assert isinstance(x[1], item_types)
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
                assert len(items) in (1, 2), items
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
                if want_meta and isinstance(item, real_tree_types):
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

def augment_item_meta(repo, item, *, include_size=False, public=False):
    """Ensure item has a Metadata instance for item.meta.  If
    item.meta is currently a mode, replace it with a compatible "fake"
    Metadata instance.  If include_size is true, ensure item.meta.size
    is correct, computing it if needed.  If public is true, produce
    metadata suitable for "public consumption", e.g. via
    ls/fuse/web. This, for example, sets dir sizes to 0. If item.meta
    is a Metadata instance, this call may modify it in place or
    replace it.

    """
    def maybe_public(mode, size):
        if public and S_ISDIR(mode) and size is None:
            return 0
        return size
    # If we actually had parallelism, we'd need locking...
    assert repo
    m = item.meta
    if isinstance(m, Metadata):
        if include_size and m.size is None:
            m.size = maybe_public(m.mode, _compute_item_size(repo, item))
            return item._replace(meta=m)
        return item
    # m is mode
    meta = Metadata()
    meta.mode = m
    if S_ISLNK(m):
        if isinstance(item, FakeLink):
            target = item.target
        else:
            target = _readlink(repo, item.oid)
        meta.symlink_target = target
        meta.size = len(target)
    elif include_size:
        meta.size = maybe_public(m, _compute_item_size(repo, item))
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

def ensure_item_has_metadata(repo, item, *, include_size=False, public=False):
    """If item is a directory, attempt to find and add its metadata.  If
    the item still doesn't have a Metadata instance for item.meta,
    give it one via augment_item_meta().  May be useful for the output
    of contents().

    """
    return augment_item_meta(repo,
                             fill_in_metadata_if_dir(repo, item),
                             include_size=include_size,
                             public=public)

def join(repo, ref):
    """Generate a list of the content of all blobs that can be reached
    from an object.  The hash given in 'id' must point to a blob, a tree
    or a commit. The content of all blobs that can be seen from trees or
    commits will be added to the list.
    """
    def _join(oidx, typ, size, it, path):
        if typ == b'blob':
            yield from it
        elif typ == b'tree':
            treefile = b''.join(it)
            for ent_mode, ent_name, ent_oid in tree_iter(treefile):
                yield from _join(*get_oidx(repo, hexlify(ent_oid)), path + [ent_name])
        elif typ == b'commit':
            treeline = b''.join(it).split(b'\n')[0]
            assert treeline.startswith(b'tree ')
            tree_oidx = treeline[5:]
            path += [oidx, tree_oidx]
            yield from _join(*get_oidx(repo, tree_oidx), path)
        else:
            raise GitError(f'type {typ!r} is not blob/tree/commit at {path!r}')

    got = get_ref(repo, ref)
    if not got[0]:
        raise GitError(f'ref {ref} does not exist') # eventually some ENOENT?
    yield from _join(*got, [ref])
