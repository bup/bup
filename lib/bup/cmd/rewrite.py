
from binascii import hexlify, unhexlify
from contextlib import closing
from itertools import chain
from stat import S_ISDIR, S_ISLNK, S_ISREG
import os
import sqlite3

from bup import hashsplit, git, options, repo, metadata, vfs
from bup.compat import argv_bytes
from bup.hashsplit import GIT_MODE_FILE, GIT_MODE_SYMLINK, GIT_MODE_TREE
from bup.helpers import \
    (handle_ctrl_c, path_components,
     valid_save_name, log,
     parse_rx_excludes,
     qprogress,
     reprogress,
     should_rx_exclude_path)
from bup.io import path_msg, qsql_id
from bup.tree import Stack
from bup.repo import make_repo
from bup.config import derive_repo_addr, ConfigError


optspec = """
bup rewrite -s srcrepo <branch-name>
--
s,source=        source repository
r,remote=        remote destination repository
work-db=         work database filename (required, can be deleted after running)
exclude-rx=      skip paths matching the unanchored regex (may be repeated)
exclude-rx-from= skip --exclude-rx patterns in file (may be repeated)
"""

def prep_mapping_table(db, split_cfg):
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

def previous_conversion(dstrepo, item, vfs_dir, db, mapping):
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

def vfs_walk_recursively(srcrepo, dstrepo, vfs_item, excludes, db, mapping,
                         fullname=b''):
    for name, item in vfs.contents(srcrepo, vfs_item):
        if name in (b'.', b'..'):
            continue
        itemname = fullname + b'/' + name
        check_name = itemname + (b'/' if S_ISDIR(vfs.item_mode(item)) else b'')
        if should_rx_exclude_path(check_name, excludes):
            continue
        if S_ISDIR(vfs.item_mode(item)):
            item, oid, _ = previous_conversion(dstrepo, item, True, db, mapping)
            if oid is None:
                yield from vfs_walk_recursively(srcrepo, dstrepo, item,
                                                excludes, db, mapping,
                                                fullname=itemname)
            # and the dir itself
            yield itemname + b'/', item
        else:
            yield itemname, item

def rewrite_link(item, item_mode, name, srcrepo, dstrepo, stack):
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

def rewrite_item(item, commit_name, fullname, srcrepo, src, dstrepo, split_cfg,
                 stack, wdbc, mapping):
    dirn, filen = os.path.split(fullname)
    assert dirn.startswith(b'/')
    dirp = path_components(dirn)

    # If switching to a new sub-tree, finish the current sub-tree.
    while list(stack.path()) > [x[0] for x in dirp]:
        stack.pop()

    # If switching to a new sub-tree, start a new sub-tree.
    for path_component in dirp[len(stack):]:
        dir_name, fs_path = path_component

        dir_item = vfs.resolve(srcrepo, src + b'/' + commit_name + b'/' + fs_path)
        meta = dir_item[-1][1].meta
        if not isinstance(meta, metadata.Metadata):
            meta = None
        stack.push(dir_name, meta)

    # First, things that can't be affected by the rewrite
    item_mode = vfs.item_mode(item)
    if S_ISLNK(item_mode):
        rewrite_link(item, item_mode, filen, srcrepo, dstrepo, stack)
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
        previous_conversion(dstrepo, item, not filen, wdbc, mapping)

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

def rewrite_branch(srcrepo, src, dstrepo, dst, excludes, workdb, fatal):
    # Currently, the workdb must always be ready to commit (see finally below)
    srcref = b'refs/heads/%s' % src
    dstref = b'refs/heads/%s' % dst
    if dstrepo.read_ref(dstref) is not None:
        fatal(f'branch already exists: {path_msg(dst)}')
    try:
        split_cfg = hashsplit.configuration(dstrepo.config_get)
    except ConfigError as ex:
        fatal(ex)
    split_trees = dstrepo.config_get(b'bup.split.trees', opttype='bool')

    vfs_branch = vfs.resolve(srcrepo, src)
    item = vfs_branch[-1][1]
    if not item:
        fatal(f'cannot access {path_msg(src)} in source\n')
    commit_oid_name = {
        c[1].coid: c[0]
        for c in vfs.contents(srcrepo, item)
        if isinstance(c[1], vfs.Commit)
    }
    commits = list(srcrepo.rev_list(hexlify(item.oid), parse=vfs.parse_rev,
                                    format=b'%T %at'))
    commits.reverse()
    with closing(workdb.cursor()) as wdbc:
        try:
            mapping = prep_mapping_table(wdbc, split_cfg)

            # Maintain a stack of information representing the current
            # location in the archive being constructed.
            parent = None
            i, n = 0, len(commits)
            for commit, (tree, timestamp) in commits:
                i += 1
                stack = Stack(dstrepo, split_cfg)

                commit_name = commit_oid_name[unhexlify(commit)]
                pm = f'{path_msg(src)}/{path_msg(commit_name)}'
                orig_oidm = commit[:12].decode("ascii")
                qprogress(f'{i}/{n} {orig_oidm} {pm}\r')

                citem = vfs.Commit(meta=vfs.default_dir_mode, oid=tree,
                                   coid=commit)
                for fullname, item in vfs_walk_recursively(srcrepo, dstrepo,
                                                           citem, excludes,
                                                           wdbc, mapping):
                    rewrite_item(item, commit_name, fullname, srcrepo, src,
                                 dstrepo, split_cfg, stack, wdbc, mapping)

                while len(stack) > 1: # pop all parts above root folder
                    stack.pop()
                tree = stack.pop() # and the root to get the tree

                commit_it = srcrepo.cat(commit)
                next(commit_it)
                ci = git.parse_commit(b''.join(commit_it))
                author = ci.author_name + b' <' + ci.author_mail + b'>'
                committer = ci.committer_name + b' <' + ci.committer_mail + b'>'
                newref = dstrepo.write_commit(tree, parent,
                                              author,
                                              ci.author_sec,
                                              ci.author_offset,
                                              committer,
                                              ci.committer_sec,
                                              ci.committer_offset,
                                              ci.message)
                parent = newref
                new_oidm = newref.hex()[:12]
                log(f'{orig_oidm} -> {new_oidm} {pm}\n')
                reprogress()

            dstrepo.update_ref(dstref, newref, None)
        finally:
            workdb.commit() # the workdb is always ready for commit

def main(argv):

    handle_ctrl_c()

    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])

    if len(extra) != 1:
        o.fatal('no branch name given')

    exclude_rxs = parse_rx_excludes(flags, o.fatal)

    src = argv_bytes(extra[0])
    if b':' in src:
        src, dst = src.split(b':', 1)
    else:
        dst = src
    if not valid_save_name(src):
        o.fatal(f'invalid branch name: {path_msg(src)}')
    if not valid_save_name(dst):
        o.fatal(f'invalid branch name: {path_msg(dst)}')

    if opt.remote:
        opt.remote = argv_bytes(opt.remote)

    if not opt.work_db:
        o.fatal('--work-db argument is required')

    workdb_conn = sqlite3.connect(opt.work_db)
    workdb_conn.text_factory = bytes

    # FIXME: support remote source repos ... probably after we unify
    # the handling?
    # Leave db commits to the sub-functions doing the work.
    with repo.LocalRepo(argv_bytes(opt.source)) as srcrepo, \
         make_repo(derive_repo_addr(remote=opt.remote, die=o.fatal)) as dstrepo, \
         closing(workdb_conn):
        rewrite_branch(srcrepo, src, dstrepo, dst, exclude_rxs, workdb_conn,
                       o.fatal)

