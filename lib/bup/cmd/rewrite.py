
from binascii import hexlify, unhexlify
from contextlib import closing
from itertools import chain
from stat import S_ISDIR, S_ISLNK, S_ISREG
import os
import sqlite3

from bup import hashsplit, git, options, repo, metadata, vfs
from bup.compat import argv_bytes
from bup.hashsplit import GIT_MODE_FILE, GIT_MODE_SYMLINK
from bup.helpers import \
    (handle_ctrl_c, path_components,
     valid_save_name, log,
     parse_rx_excludes,
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
    settings = [str(x) for x in chain.from_iterable(sorted(split_cfg.items()))]
    for x in settings: assert '_' not in x
    table_id = f'bup_rewrite_mapping_to_bits_{"_".join(settings)}'
    table_id = qsql_id(table_id)
    db.execute(f'create table if not exists {table_id}'
               '    (src blob,'
               '     dst blob not null,'
               '     vfs_mode integer,'
               '     git_mode integer,'
               '     size integer,'
               '     primary key (src, vfs_mode))'
               '    without rowid')
    return table_id

def previous_conversion(dstrepo, item, vfs_dir, db, mapping):
    """Return (replacement_item, converted_oid, mode) for the given
    item if any, *and* if the dstrepo has the item.oid. If not,
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

    db.execute(f'select dst, vfs_mode, git_mode, size from {mapping}'
               ' where src = ? and vfs_mode = ?',
               (item.oid, item_mode))
    data = db.fetchone()
    if not data:
        return item, None, None, None
    assert db.fetchone() is None
    dst, vfs_mode, git_mode, size = data
    assert vfs_mode == item_mode
    # augment the size if appropriate
    if size is not None and isinstance(item.meta, metadata.Metadata):
        if item.meta.size is not None:
            assert item.meta.size == size
        else: # must not modify vfs results (see vfs docs)
            item = vfs.copy_item(item)
            item.meta.size = size
    # if we have it in the DB and in the destination repo, return it
    if dstrepo.exists(dst):
        return item, dst, vfs_mode, git_mode
    # this only happens if you reuse a database
    return item, None, None, None

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
            item, oid, _, _ = previous_conversion(dstrepo, item, True, db, mapping)
            if oid is None:
                yield from vfs_walk_recursively(srcrepo, dstrepo, item,
                                                excludes, db, mapping,
                                                fullname=itemname)
            # and the dir itself
            yield itemname + b'/', item
        else:
            yield itemname, item

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

    item, oid, vfs_mode, git_mode = \
        previous_conversion(dstrepo, item, not filen, wdbc, mapping)

    if not filen:
        if len(stack) == 1:
            return # We're at the top level -- keep the current root dir
        # Since there's no filename, this is a subdir -- finish it.
        newtree = stack.pop(override_tree=oid)
        if oid is None:
            assert vfs_mode is None, item.oid.hex()
            assert git_mode is None, item.oid.hex()
            vfs_mode = vfs.item_mode(item)
            wdbc.execute(f'insert into {mapping}'
                         '   (src, dst, vfs_mode) values (?, ?, ?)',
                         (item.oid, newtree, vfs_mode))
        return

    # already converted - oid and mode are known
    if oid is not None:
        assert vfs_mode is not None, oid.hex()
        assert git_mode is not None, oid.hex()
        stack.append_to_current(filen, vfs_mode, git_mode, oid, item.meta)
        return

    vfs_mode = vfs.item_mode(item)
    item_size = None
    if S_ISREG(vfs_mode):
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
    elif S_ISDIR(vfs_mode):
        assert False  # handled above
    elif S_ISLNK(vfs_mode):
        target = vfs.readlink(srcrepo, item)
        git_mode, oid = GIT_MODE_SYMLINK, dstrepo.write_symlink(target)
        if isinstance(item.meta, metadata.Metadata):
            if item.meta.size is None:
                # must not modify vfs results (see vfs docs)
                item = vfs.copy_item(item)
                item.meta.size = len(item.meta.symlink_target)
            else:
                assert item.meta.size == len(item.meta.symlink_target)
        item_size = len(target)
    else:
        # Everything else should be fully described by its metadata,
        # so just record an empty blob, so the paths in the tree and
        # .bupm will match up.
        assert item_size is None
        git_mode, oid = GIT_MODE_FILE, dstrepo.write_data(b'')

    wdbc.execute(f'select src, dst, vfs_mode, size from {mapping}'
                 '  where src = ? and vfs_mode = ?',
                 (item.oid, vfs_mode))
    row = wdbc.fetchone()
    assert wdbc.fetchone() is None
    if row: # reusing previously populated db
        assert row == (item.oid, oid, vfs_mode, git_mode, item_size)
    else:
        wdbc.execute(f'insert into {mapping}'
                     '   (src, dst, vfs_mode, git_mode, size)'
                     '   values (?, ?, ?, ?, ?)',
                     (item.oid, oid, vfs_mode, git_mode, item_size))
    stack.append_to_current(filen, vfs_mode, git_mode, oid, item.meta)

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
            for commit, (tree, timestamp) in commits:
                stack = Stack(dstrepo, split_cfg)

                commit_name = commit_oid_name[unhexlify(commit)]
                log(b'Rewriting /%s/%s/ (%s)...\n'
                    % (src, commit_name, commit[:12]))

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

