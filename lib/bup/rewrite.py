
from binascii import hexlify
from contextlib import ExitStack, closing, nullcontext
from itertools import chain
from os.path import join as pj
from stat import S_ISDIR, S_ISLNK, S_ISREG
import os, sqlite3, time

from bup import hashsplit, metadata, vfs
from bup.git import get_cat_data, parse_commit
from bup.hashsplit import GIT_MODE_FILE, GIT_MODE_SYMLINK, GIT_MODE_TREE
from bup.helpers import \
    hostname, path_components, should_rx_exclude_path, temp_dir
from bup.io import qsql_id
from bup.pwdgrp import userfullname, username
from bup.tree import Stack


def _fs_path_from_vfs(path):
    fs = b'/'.join(x[0] for x in path)
    if not S_ISDIR(vfs.item_mode(path[-1][1])):
        return fs
    return fs + b'/'


def _prep_mapping_table(db, split_cfg):
    # This currently only needs to track items that may be split,
    # depending on the current repo settings (e.g. files and
    # directories); it records the result so we can re-use it if we
    # encounter the item again.
    settings = [str(x) for x in chain.from_iterable(sorted(split_cfg.items()))]
    for x in settings: assert '_' not in x
    table_id = f'bup_rewrite_mapping_to_bits_{"_".join(settings)}'
    table_id = qsql_id(table_id)
    db.execute(f'create table if not exists {table_id}'
               '    (src blob primary key,'
               '     dst blob not null,'
               '     chunked integer,' # is this a chunked file
               '     size integer)' # only for files
               '    without rowid')
    return table_id

def _previous_conversion(dstrepo, item, vfs_dir, db, mapping):
    """Return (replacement_item, converted_oid, git_mode) for the
    given item if any, *and* if the dstrepo has the item.oid. If not,
    converted_oid and mode will be None. The replacement_item will
    either be item, or an augmented copy of item, (e.g. with a proper
    size) that should be used instead of item.

    """
    if isinstance(item.meta, metadata.Metadata):
        size = item.meta.size
        item_mode = item.meta.mode
    else:
        size = None
        item_mode = item.meta

    db.execute(f'select dst, chunked, size from {mapping} where src = ?',
               (item.oid,))
    data = db.fetchone()
    if not data:
        return item, None, None
    assert db.fetchone() is None
    dst, chunked, size = data
    if chunked:
        assert S_ISREG(item_mode)
    if not dstrepo.exists(dst):
        # only happens if you reuse a database
        return item, None, None
    # augment the size if appropriate
    if size is not None and isinstance(item.meta, metadata.Metadata):
        if item.meta.size is not None:
            assert item.meta.size == size
        else: # must not modify vfs results (see vfs docs)
            item = vfs.copy_item(item)
            item.meta.size = size
    # it's in the DB and in the destination repo
    if chunked is None: # dir, not file
        return item, dst, None
    return item, dst, GIT_MODE_TREE if chunked else GIT_MODE_FILE

def _vfs_walk_recursively(srcrepo, dstrepo, path, excludes, db, mapping):
    item = path[-1][1]
    assert len(path) >= 3
    # drop branch/DATE
    fs_path_in_save = _fs_path_from_vfs((path[0],) + path[3:])
    for entry in vfs.contents(srcrepo, item):
        name, sub_item = entry
        sub_path = path + (entry,)
        if name in (b'.', b'..'):
            continue
        sub_fs_path_in_save = pj(fs_path_in_save, name)
        if S_ISDIR(vfs.item_mode(sub_item)):
            sub_fs_path_in_save += b'/'
        if should_rx_exclude_path(sub_fs_path_in_save, excludes):
            continue
        if S_ISDIR(vfs.item_mode(sub_item)):
            conv_item, oid, _ = \
                _previous_conversion(dstrepo, sub_item, True, db, mapping)
            if conv_item is not sub_item:
                sub_path = sub_path[:-1] + ((sub_path[-1][0], conv_item),)
            if oid is None:
                yield from _vfs_walk_recursively(srcrepo, dstrepo, sub_path,
                                                 excludes, db, mapping)
        yield sub_path

def _rewrite_link(item, item_mode, name, srcrepo, dstrepo, stack):
    assert isinstance(name, bytes)
    target = vfs.readlink(srcrepo, item)
    git_mode, oid = GIT_MODE_SYMLINK, dstrepo.write_symlink(target)
    if isinstance(item.meta, metadata.Metadata):
        if item.meta.size is None:
            # must not modify vfs results (see vfs docs)
            item = vfs.copy_item(item)
            item.meta.size = len(item.meta.symlink_target)
        else:
            assert item.meta.size == len(item.meta.symlink_target)
    stack.append_to_current(name, item_mode, git_mode, oid, item.meta)

def _rewrite_save_item(save_path, path, srcrepo, dstrepo, split_cfg, stack,
                       wdbc, mapping):
    # save_path is the vfs path to the save ref, e.g. to branch/DATE
    fs_path = _fs_path_from_vfs(path[3:]) # not including /branch/DATE
    assert not fs_path.startswith(b'/') # because resolve(parent=...)
    dirn, filen = os.path.split(b'/' + fs_path)
    assert dirn.startswith(b'/')
    dirp = path_components(dirn)

    # If switching to a new sub-tree, finish the current sub-tree.
    while list(stack.path()) > [x[0] for x in dirp]:
        stack.pop()

    # If switching to a new sub-tree, start a new sub-tree.
    comp_parent = None
    for path_component in dirp[len(stack):]:
        comp_name, comp_path = path_component
        if comp_parent:
            dir_res = vfs.resolve(srcrepo, comp_name, parent=comp_parent)
        else:
            full_comp_path = b'/'.join([x[0] for x in save_path]) + comp_path
            dir_res = vfs.resolve(srcrepo, full_comp_path)
        meta = dir_res[-1][1].meta
        if not isinstance(meta, metadata.Metadata):
            meta = None
        stack.push(comp_name, meta)
        comp_parent = dir_res

    item = path[-1][1]

    # First, things that can't be affected by the rewrite
    item_mode = vfs.item_mode(item)
    if S_ISLNK(item_mode):
        _rewrite_link(item, item_mode, filen, srcrepo, dstrepo, stack)
        return
    if not S_ISREG(item_mode) and not S_ISDIR(item_mode):
        # Everything here (pipes, devices, etc.) should be fully
        # described by its metadata, and so bup just saves an empty
        # "placeholder" blob in the git tree (so the tree and .bupm
        # will match up).
        git_mode, oid = GIT_MODE_FILE, dstrepo.write_data(b'')
        stack.append_to_current(filen, item_mode, git_mode, oid, item.meta)
        return

    item, oid, git_mode = \
        _previous_conversion(dstrepo, item, not filen, wdbc, mapping)

    if not filen:
        # Since there's no filename, this is a subdir -- finish it.
        assert S_ISDIR(item_mode)
        assert git_mode is None, item.oid.hex() # for both exists and not
        if len(stack) == 1:
            return # We're at the top level -- keep the current root dir
        newtree = stack.pop(override_tree=oid)
        if oid is None:
            wdbc.execute(f'insert into {mapping} (src, dst) values (?, ?)',
                         (item.oid, newtree))
        return

    assert S_ISREG(item_mode)
    if oid is not None:
        # already converted - oid and mode are known
        assert git_mode in (GIT_MODE_TREE, GIT_MODE_FILE)
        stack.append_to_current(filen, item_mode, git_mode, oid, item.meta)
        return

    item_size = None
    item_size = 0
    def write_data(data):
        nonlocal item_size
        item_size += len(data)
        return dstrepo.write_data(data)
    with vfs.tree_data_reader(srcrepo, item.oid) as f:
        git_mode, oid = hashsplit.split_to_blob_or_tree(
            write_data, dstrepo.write_tree,
            hashsplit.from_config([f], split_cfg))
    if isinstance(item.meta, metadata.Metadata):
        if item.meta.size is None:
            # must not modify vfs results (see vfs docs)
            item = vfs.copy_item(item)
            item.meta.size = item_size
        else:
            assert item.meta.size == item_size
    chunked = 1 if S_ISDIR(git_mode) else 0

    wdbc.execute(f'select src, dst, chunked, size from {mapping} where src = ?',
                 (item.oid,))
    row = wdbc.fetchone()
    assert wdbc.fetchone() is None
    if row:
        assert row == (item.oid, oid, chunked, item_size)
    else:
        wdbc.execute(f'insert into {mapping} (src, dst, chunked, size)'
                     '   values (?, ?, ?, ?)',
                     (item.oid, oid, chunked, item_size))
    stack.append_to_current(filen, item_mode, git_mode, oid, item.meta)

class Rewriter:
    def __init__(self, *, split_cfg, db=None):
        assert isinstance(db, (bytes, type(None)))
        self._context = nullcontext()
        with ExitStack() as ctx:
            self._split_cfg = split_cfg
            self._db_path = db
            if db:
                self._db_tmpdir = None
            else:
                self._db_tmpdir = \
                    ctx.enter_context(temp_dir(prefix='bup-rewrite-'))
                self._db_path = f'{self._db_tmpdir}/db'
            self._db_conn = sqlite3.connect(self._db_path)
            ctx.enter_context(closing(self._db_conn))
            self._db_conn.text_factory = bytes
            with closing(self._db_conn.cursor()) as cur:
                self._mapping = _prep_mapping_table(cur, split_cfg)
            self._context = ctx.pop_all()

    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        with self._context:
            pass

    def append_save(self, save_path, parent, srcrepo, dstrepo, excludes):
        # Strict for now
        assert isinstance(parent, (bytes, type(None))), parent
        if parent:
            assert len(parent) == 20, parent
        assert len(save_path) == 3, (len(save_path), save_path)
        assert isinstance(save_path[1][1], vfs.RevList)
        leaf_name, leaf_item = save_path[2]
        if isinstance(leaf_item, vfs.FakeLink):
            # For now, vfs.contents() does not resolve the one FakeLink
            assert leaf_name == b'latest', save_path
            res = srcrepo.resolve(leaf_item.target, parent=save_path[:-1],
                                  follow=False, want_meta=False)
            leaf_name, leaf_item = res[-1]
            save_path = res
        assert isinstance(leaf_item, vfs.Commit), leaf_item
        # Currently, the workdb must always be ready to commit (see finally below)
        with closing(self._db_conn.cursor()) as dbc:
            try:
                # Maintain a stack of information representing the current
                # location in the archive being constructed.
                stack = Stack(dstrepo, self._split_cfg)

                for path in _vfs_walk_recursively(srcrepo, dstrepo, save_path,
                                                  excludes, dbc, self._mapping):
                    _rewrite_save_item(save_path, path, srcrepo, dstrepo,
                                       self._split_cfg, stack, dbc,
                                       self._mapping)

                while len(stack) > 1: # pop all parts above root folder
                    stack.pop()
                tree = stack.pop() # and the root to get the tree

                save_oidx = hexlify(save_path[2][1].coid)
                ci = parse_commit(get_cat_data(srcrepo.cat(save_oidx), b'commit'))
                author = ci.author_name + b' <' + ci.author_mail + b'>'
                committer = b'%s <%s@%s>' % (userfullname(), username(), hostname())
                return (dstrepo.write_commit(tree, parent,
                                             author,
                                             ci.author_sec,
                                             ci.author_offset,
                                             committer, time.time(), None,
                                             ci.message),
                        tree)
            finally:
                self._db_conn.commit() # the workdb is always ready for commit
