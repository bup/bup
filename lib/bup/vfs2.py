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
Make a copy to modify via item.meta.copy() if needed.

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
a directory is stored inside the directory.

At the moment tagged commits (e.g. /.tag/some-commit) are represented
as an item that is indistinguishable from a normal directory, so you
cannot assume that the oid of an item satisfying
S_ISDIR(item_mode(item)) refers to a tree.

"""

from __future__ import print_function
from collections import namedtuple
from errno import ELOOP, ENOENT, ENOTDIR
from itertools import chain, dropwhile, izip
from stat import S_IFDIR, S_IFLNK, S_IFREG, S_ISDIR, S_ISLNK, S_ISREG
from time import localtime, strftime
import exceptions, re, sys

from bup import client, git, metadata
from bup.git import BUP_CHUNKED, cp, get_commit_items, parse_commit, tree_decode
from bup.helpers import debug2, last
from bup.metadata import Metadata
from bup.repo import LocalRepo, RemoteRepo


class IOError(exceptions.IOError):
    def __init__(self, errno, message):
        exceptions.IOError.__init__(self, errno, message)

class Loop(IOError):
    def __init__(self, message, terminus=None):
        IOError.__init__(self, ELOOP, message)
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

def _normal_or_chunked_file_size(repo, oid):
    """Return the size of the normal or chunked file indicated by oid."""
    # FIXME: --batch-format CatPipe?
    it = repo.cat(oid.encode('hex'))
    _, obj_t, size = next(it)
    ofs = 0
    while obj_t == 'tree':
        mode, name, last_oid = last(tree_decode(''.join(it)))
        ofs += int(name, 16)
        it = repo.cat(last_oid.encode('hex'))
        _, obj_t, size = next(it)
    return ofs + sum(len(b) for b in it)

def _tree_chunks(repo, tree, startofs):
    "Tree should be a sequence of (name, mode, hash) as per tree_decode()."
    assert(startofs >= 0)
    # name is the chunk's hex offset in the original file
    tree = dropwhile(lambda (_1, name, _2): int(name, 16) < startofs, tree)
    for mode, name, oid in tree:
        ofs = int(name, 16)
        skipmore = startofs - ofs
        if skipmore < 0:
            skipmore = 0
        it = repo.cat(oid.encode('hex'))
        _, obj_t, size = next(it)
        data = ''.join(it)            
        if S_ISDIR(mode):
            assert obj_t == 'tree'
            for b in _tree_chunks(repo, tree_decode(data), skipmore):
                yield b
        else:
            assert obj_t == 'blob'
            yield data[skipmore:]

class _ChunkReader:
    def __init__(self, repo, oid, startofs):
        it = repo.cat(oid.encode('hex'))
        _, obj_t, size = next(it)
        isdir = obj_t == 'tree'
        data = ''.join(it)
        if isdir:
            self.it = _tree_chunks(repo, tree_decode(data), startofs)
            self.blob = None
        else:
            self.it = None
            self.blob = data[startofs:]
        self.ofs = startofs

    def next(self, size):
        out = ''
        while len(out) < size:
            if self.it and not self.blob:
                try:
                    self.blob = self.it.next()
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
        if ofs < 0:
            raise IOError(errno.EINVAL, 'Invalid argument')
        if ofs > self._compute_size():
            raise IOError(errno.EINVAL, 'Invalid argument')
        self.ofs = ofs

    def tell(self):
        return self.ofs

    def read(self, count=-1):
        if count < 0:
            count = self._compute_size() - self.ofs
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

_multiple_slashes_rx = re.compile(r'//+')

def _decompose_path(path):
    """Return a reversed list of path elements, omitting any occurrences
    of "."  and ignoring any leading or trailing slash."""
    path = re.sub(_multiple_slashes_rx, '/', path)
    if path.startswith('/'):
        path = path[1:]
    if path.endswith('/'):
        path = path[:-1]
    result = [x for x in path.split('/') if x != '.']
    result.reverse()
    return result
    

Item = namedtuple('Item', ('meta', 'oid'))
Chunky = namedtuple('Chunky', ('meta', 'oid'))
Root = namedtuple('Root', ('meta'))
Tags = namedtuple('Tags', ('meta'))
RevList = namedtuple('RevList', ('meta', 'oid'))

_root = Root(meta=default_dir_mode)
_tags = Tags(meta=default_dir_mode)

def copy_item(item):
    """Return a completely independent copy of item, such that
    modifications will not affect the original.

    """
    meta = getattr(item, 'meta', None)
    if not meta:
        return item
    return(item._replace(meta=meta.copy()))

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

def _tree_data_and_bupm(repo, oid):
    """Return (tree_bytes, bupm_oid) where bupm_oid will be None if the
    tree has no metadata (i.e. older bup save, or non-bup tree).

    """    
    assert len(oid) == 20
    it = repo.cat(oid.encode('hex'))
    _, item_t, size = next(it)
    data = ''.join(it)
    if item_t == 'commit':
        commit = parse_commit(data)
        it = repo.cat(commit.tree)
        _, item_t, size = next(it)
        data = ''.join(it)
        assert item_t == 'tree'
    elif item_t != 'tree':
        raise Exception('%r is not a tree or commit' % oid.encode('hex'))
    for _, mangled_name, sub_oid in tree_decode(data):
        if mangled_name == '.bupm':
            return data, sub_oid
        if mangled_name > '.bupm':
            break
    return data, None

def _find_dir_item_metadata(repo, item):
    """Return the metadata for the tree or commit item, or None if the
    tree has no metadata (i.e. older bup save, or non-bup tree).

    """
    tree_data, bupm_oid = _tree_data_and_bupm(repo, item.oid)
    if bupm_oid:
        with _FileReader(repo, bupm_oid) as meta_stream:
            return _read_dir_meta(meta_stream)
    return None

def _readlink(repo, oid):
    return ''.join(repo.join(oid.encode('hex')))

def readlink(repo, item):
    """Return the link target of item, which must be a symlink.  Reads the
    target from the repository if necessary."""
    assert repo
    assert S_ISLNK(item_mode(item))
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
        return len(_readlink(repo, item.oid))
    return 0

def item_size(repo, item):
    """Return the size of item, computing it if necessary."""
    m = item.meta
    if isinstance(m, Metadata) and m.size is not None:
        return m.size
    return _compute_item_size(repo, item)

def fopen(repo, item):
    """Return an open reader for the given file item."""
    assert repo
    assert S_ISREG(item_mode(item))
    return _FileReader(repo, item.oid)

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
        target = _readlink(repo, item.oid)
        meta.symlink_target = target
        meta.size = len(target)
    elif include_size:
        meta.size = _compute_item_size(repo, item)
    return item._replace(meta=meta)

def _commit_meta_from_auth_sec(author_sec):
    m = Metadata()
    m.mode = default_dir_mode
    m.uid = m.gid = m.size = 0
    m.atime = m.mtime = m.ctime = author_sec * 10**9
    return m

def _commit_meta_from_oidx(repo, oidx):
    it = repo.cat(oidx)
    _, typ, size = next(it)
    assert typ == 'commit'
    author_sec = parse_commit(''.join(it)).author_sec
    return _commit_meta_from_auth_sec(author_sec)

def parse_rev_auth_secs(f):
    tree, author_secs = f.readline().split(None, 2)
    return tree, int(author_secs)

def root_items(repo, names=None):
    """Yield (name, item) for the items in '/' in the VFS.  Return
    everything if names is logically false, otherwise return only
    items with a name in the collection.

    """
    # FIXME: what about non-leaf refs like 'refs/heads/foo/bar/baz?

    global _root, _tags
    if not names:
        yield '.', _root
        yield '.tag', _tags
        # FIXME: maybe eventually support repo.clone() or something
        # and pass in two repos, so we can drop the tuple() and stream
        # in parallel (i.e. meta vs refs).
        for name, oid in tuple(repo.refs([], limit_to_heads=True)):
            assert(name.startswith('refs/heads/'))
            name = name[11:]
            m = _commit_meta_from_oidx(repo, oid.encode('hex'))
            yield name, RevList(meta=m, oid=oid)
        return

    if '.' in names:
        yield '.', _root
    if '.tag' in names:
        yield '.tag', _tags
    for ref in names:
        if ref in ('.', '.tag'):
            continue
        it = repo.cat(ref)
        oidx, typ, size = next(it)
        if not oidx:
            for _ in it: pass
            continue
        assert typ == 'commit'
        commit = parse_commit(''.join(it))
        yield ref, RevList(meta=_commit_meta_from_auth_sec(commit.author_sec),
                           oid=oidx.decode('hex'))

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
    
def tree_items(oid, tree_data, names=frozenset(tuple()), bupm=None):

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
        yield '.', Item(oid=oid, meta=dot_meta)
        tree_entries = ordered_tree_entries(tree_data, bupm)
        for name, mangled_name, kind, gitmode, ent_oid in tree_entries:
            if mangled_name == '.bupm':
                continue
            assert name != '.'
            yield name, tree_item(ent_oid, kind, gitmode)
        return

    # Assumes the tree is properly formed, i.e. there are no
    # duplicates, and entries will be in git tree order.
    if type(names) not in (frozenset, set):
        names = frozenset(names)
    remaining = len(names)

    # Account for the bupm sort order issue (cf. ordered_tree_entries above)
    last_name = max(names) if bupm else max(names) + '/'

    if '.' in names:
        dot_meta = _read_dir_meta(bupm) if bupm else default_dir_mode
        yield '.', Item(oid=oid, meta=dot_meta)
        if remaining == 1:
            return
        remaining -= 1

    tree_entries = ordered_tree_entries(tree_data, bupm)
    for name, mangled_name, kind, gitmode, ent_oid in tree_entries:
        if mangled_name == '.bupm':
            continue
        assert name != '.'
        if name not in names:
            if bupm:
                if (name + '/') > last_name:
                    break  # given git sort order, we're finished
            else:
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
        if mangled_name == '.bupm':
            bupm = _FileReader(repo, sub_oid)
            break
        if mangled_name > '.bupm':
            break
    for item in tree_items(oid, tree_data, names, bupm):
        yield item

_save_name_rx = re.compile(r'^\d\d\d\d-\d\d-\d\d-\d{6}$')
        
def revlist_items(repo, oid, names):
    assert len(oid) == 20
    oidx = oid.encode('hex')

    # There might well be duplicate names in this dir (time resolution is secs)
    names = frozenset(name for name in (names or tuple()) \
                      if _save_name_rx.match(name) or name in ('.', 'latest'))

    # Do this before we open the rev_list iterator so we're not nesting
    if (not names) or ('.' in names):
        yield '.', RevList(oid=oid, meta=_commit_meta_from_oidx(repo, oidx))
    
    revs = repo.rev_list((oidx,), format='%T %at', parse=parse_rev_auth_secs)
    first_rev = next(revs, None)
    revs = chain((first_rev,), revs)

    if not names:
        for commit, (tree_oidx, utc) in revs:
            assert len(tree_oidx) == 40
            name = strftime('%Y-%m-%d-%H%M%S', localtime(utc))
            yield name, Item(meta=default_dir_mode, oid=tree_oidx.decode('hex'))
        if first_rev:
            commit, (tree_oidx, utc) = first_rev
            yield 'latest', Item(meta=default_dir_mode,
                                 oid=tree_oidx.decode('hex'))
        return

    # Revs are in reverse chronological order by default
    last_name = min(names)
    for commit, (tree_oidx, utc) in revs:
        assert len(tree_oidx) == 40
        name = strftime('%Y-%m-%d-%H%M%S', localtime(utc))
        if name < last_name:
            break
        if not name in names:
            continue
        yield name, Item(meta=default_dir_mode, oid=tree_oidx.decode('hex'))

    # FIXME: need real short circuit...
    for _ in revs:
        pass
        
    if first_rev and 'latest' in names:
        commit, (tree_oidx, utc) = first_rev
        yield 'latest', Item(meta=default_dir_mode, oid=tree_oidx.decode('hex'))

def tags_items(repo, names):
    global _tags

    def tag_item(oid):
        assert len(oid) == 20
        oidx = oid.encode('hex')
        it = repo.cat(oidx)
        _, typ, size = next(it)
        if typ == 'commit':
            tree_oid = parse_commit(''.join(it)).tree.decode('hex')
            assert len(tree_oid) == 20
            # FIXME: more efficient/bulk?
            return RevList(meta=_commit_meta_from_oidx(repo, oidx), oid=oid)
        for _ in it: pass
        if typ == 'blob':
            return Item(meta=default_file_mode, oid=oid)
        elif typ == 'tree':
            return Item(meta=default_dir_mode, oid=oid)
        raise Exception('unexpected tag type ' + typ + ' for tag ' + name)

    if not names:
        yield '.', _tags
        # We have to pull these all into ram because tag_item calls cat()
        for name, oid in tuple(repo.refs(names, limit_to_tags=True)):
            assert(name.startswith('refs/tags/'))
            name = name[10:]
            yield name, tag_item(oid)
        return

    # Assumes no duplicate refs
    if type(names) not in (frozenset, set):
        names = frozenset(names)
    remaining = len(names)
    last_name = max(names)
    if '.' in names:
        yield '.', _tags
        if remaining == 1:
            return
        remaining -= 1

    for name, oid in repo.refs(names, limit_to_tags=True):
        assert(name.startswith('refs/tags/'))
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

    Any given name might produce more than one result.  For example,
    saves to a branch that happen within the same second currently end
    up with the same VFS timestmap, i.e. /foo/2017-09-10-150833/.

    Note that want_meta is advisory.  For any given item, item.meta
    might be a Metadata instance or a mode, and if the former,
    meta.size might be None.  Missing sizes can be computed via via
    item_size() or augment_item_meta(..., include_size=True).

    Do not modify any item.meta Metadata instances directly.  If
    needed, make a copy via item.meta.copy() and modify that instead.

    """
    # Q: are we comfortable promising '.' first when no names?
    assert repo
    assert S_ISDIR(item_mode(item))
    item_t = type(item)
    if item_t == Item:
        it = repo.cat(item.oid.encode('hex'))
        _, obj_type, size = next(it)
        data = ''.join(it)
        if obj_type == 'tree':
            if want_meta:
                item_gen = tree_items_with_meta(repo, item.oid, data, names)
            else:
                item_gen = tree_items(item.oid, data, names)
        elif obj_type == 'commit':
            tree_oidx = parse_commit(data).tree
            it = repo.cat(tree_oidx)
            _, obj_type, size = next(it)
            assert obj_type == 'tree'
            tree_data = ''.join(it)
            if want_meta:
                item_gen = tree_items_with_meta(repo, tree_oidx.decode('hex'),
                                                tree_data, names)
            else:
                item_gen = tree_items(tree_oidx.decode('hex'), tree_data, names)
        else:
            for _ in it: pass
            raise Exception('unexpected git ' + obj_type)
    elif item_t == RevList:
        item_gen = revlist_items(repo, item.oid, names)
    elif item_t == Root:
        item_gen = root_items(repo, names)
    elif item_t == Tags:
        item_gen = tags_items(repo, names)
    else:
        raise Exception('unexpected VFS item ' + str(item))
    for x in item_gen:
        yield x

def _resolve_path(repo, path, parent=None, want_meta=True, deref=False):
    assert repo
    assert len(path)
    global _root
    future = _decompose_path(path)
    past = []
    if path.startswith('/'):
        assert(not parent)
        past = [('', _root)]
        if future == ['']: # path was effectively '/'
            return tuple(past)
    if not past and not parent:
        past = [('', _root)]
    if parent:
        past = [parent]
    hops = 0
    result = None
    while True:
        segment = future.pop()
        if segment == '..':
            if len(past) > 1:  # .. from / is /
                past.pop()
        else:
            parent_name, parent_item = past[-1]
            wanted = (segment,) if not want_meta else ('.', segment)
            items = tuple(contents(repo, parent_item, names=wanted,
                                   want_meta=want_meta))
            if not want_meta:
                item = items[0][1] if items else None
            else:  # First item will be '.' and have the metadata
                item = items[1][1] if len(items) == 2 else None
                dot, dot_item = items[0]
                assert dot == '.'
                past[-1] = parent_name, parent_item
            if not item:
                return tuple(past + [(segment, None)])
            mode = item_mode(item)
            if not S_ISLNK(mode):
                if not S_ISDIR(mode):
                    assert(not future)
                    return tuple(past + [(segment, item)])
                # It's treeish
                if want_meta and type(item) == Item:
                    dir_meta = _find_dir_item_metadata(repo, item)
                    if dir_meta:
                        item = item._replace(meta=dir_meta)
                if not future:
                    return tuple(past + [(segment, item)])
                past.append((segment, item))
            else:  # symlink            
                if not future and not deref:
                    return tuple(past + [(segment, item)])
                target = readlink(repo, item)
                target_future = _decompose_path(target)
                if target.startswith('/'):
                    future = target_future
                    past = [('', _root)]
                    if target_future == ['']:  # path was effectively '/'
                        return tuple(past)
                else:
                    future = future + target_future
                hops += 1
                if hops > 100:
                    raise Loop('too many symlinks encountered while resolving %r%s'
                               % (path,
                                  'relative to %r' % parent if parent else ''))
                
def lresolve(repo, path, parent=None, want_meta=True):
    """Perform exactly the same function as resolve(), except if the
     final path element is a symbolic link, don't follow it, just
     return it in the result."""
    return _resolve_path(repo, path, parent=parent, want_meta=want_meta,
                         deref=False)
                         

def resolve(repo, path, parent=None, want_meta=True):
    """Follow the path in the virtual filesystem and return a tuple
    representing the location, if any, denoted by the path.  Each
    element in the result tuple will be (name, info), where info will
    be a VFS item that can be passed to functions like item_mode().

    If a path segment that does not exist is encountered during
    resolution, the result will represent the location of the missing
    item, and that item in the result will be None.

    Any symlinks along the path, including at the end, will be
    resolved.  A Loop exception will be raised if too many symlinks
    are traversed whiile following the path.  raised if too many
    symlinks are traversed while following the path.  That exception
    is effectively like a normal ELOOP IOError exception, but will
    include a terminus element describing the location of the failure,
    which will be a tuple of (name, info) elements.

    Currently, a path ending in '/' will still resolve if it exists,
    even if not a directory.  The parent, if specified, must be a
    (name, item) tuple, and will provide the starting point for the
    resolution of the path.  Currently, the path must be relative when
    a parent is provided.  The result may include parent directly, so
    it must not be modified later.  If this is a concern, pass in
    copy_item(parent) instead.

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
    return _resolve_path(repo, path, parent=parent, want_meta=want_meta,
                         deref=True)
