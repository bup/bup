
from __future__ import absolute_import, print_function
from binascii import unhexlify
from errno import ELOOP, ENOTDIR
from os import symlink
from stat import S_IFDIR
from sys import stderr
from time import localtime, strftime

from wvtest import *

from bup import git, path, vfs
from bup.compat import environ
from bup.io import path_msg
from bup.metadata import Metadata
from bup.repo import LocalRepo, RemoteRepo
from buptest import ex, exo, no_lingering_errors, test_tempdir
from buptest.vfs import tree_dict

bup_path = path.exe()

## The clear_cache() calls below are to make sure that the test starts
## from a known state since at the moment the cache entry for a given
## item (like a commit) can change.  For example, its meta value might
## be promoted from a mode to a Metadata instance once the tree it
## refers to is traversed.

def prep_and_test_repo(name, create_repo, test_repo):
    with no_lingering_errors():
        with test_tempdir(b'bup-t' + name) as tmpdir:
            bup_dir = tmpdir + b'/bup'
            environ[b'GIT_DIR'] = bup_dir
            environ[b'BUP_DIR'] = bup_dir
            ex((bup_path, b'init'))
            git.repodir = bup_dir
            with create_repo(bup_dir) as repo:
                test_repo(repo, tmpdir)

# Currently, we just test through the repos since LocalRepo resolve is
# just a straight redirection to vfs.resolve.

def test_resolve(repo, tmpdir):
        data_path = tmpdir + b'/src'
        resolve = repo.resolve
        save_time = 100000
        save_time_str = strftime('%Y-%m-%d-%H%M%S', localtime(save_time)).encode('ascii')
        os.mkdir(data_path)
        os.mkdir(data_path + b'/dir')
        with open(data_path + b'/file', 'wb+') as tmpfile:
            tmpfile.write(b'canary\n')
        symlink(b'file', data_path + b'/file-symlink')
        symlink(b'dir', data_path + b'/dir-symlink')
        symlink(b'not-there', data_path + b'/bad-symlink')
        ex((bup_path, b'index', b'-v', data_path))
        ex((bup_path, b'save', b'-d', b'%d' % save_time, b'-tvvn', b'test',
            b'--strip', data_path))
        ex((bup_path, b'tag', b'test-tag', b'test'))

        tip_hash = exo((b'git', b'show-ref', b'refs/heads/test'))[0]
        tip_oidx = tip_hash.strip().split()[0]
        tip_oid = unhexlify(tip_oidx)
        tip_tree_oidx = exo((b'git', b'log', b'--pretty=%T', b'-n1',
                             tip_oidx))[0].strip()
        tip_tree_oid = unhexlify(tip_tree_oidx)
        tip_tree = tree_dict(repo, tip_tree_oid)
        test_revlist_w_meta = vfs.RevList(meta=tip_tree[b'.'].meta,
                                          oid=tip_oid)
        expected_latest_item = vfs.Commit(meta=S_IFDIR | 0o755,
                                          oid=tip_tree_oid,
                                          coid=tip_oid)
        expected_latest_item_w_meta = vfs.Commit(meta=tip_tree[b'.'].meta,
                                                 oid=tip_tree_oid,
                                                 coid=tip_oid)
        expected_latest_link = vfs.FakeLink(meta=vfs.default_symlink_mode,
                                            target=save_time_str)
        expected_test_tag_item = expected_latest_item

        wvstart('resolve: /')
        vfs.clear_cache()
        res = resolve(b'/')
        wvpasseq(1, len(res))
        wvpasseq(((b'', vfs._root),), res)
        ignore, root_item = res[0]
        root_content = frozenset(vfs.contents(repo, root_item))
        wvpasseq(frozenset([(b'.', root_item),
                            (b'.tag', vfs._tags),
                            (b'test', test_revlist_w_meta)]),
                 root_content)
        for path in (b'//', b'/.', b'/./', b'/..', b'/../',
                     b'/test/latest/dir/../../..',
                     b'/test/latest/dir/../../../',
                     b'/test/latest/dir/../../../.',
                     b'/test/latest/dir/../../..//',
                     b'/test//latest/dir/../../..',
                     b'/test/./latest/dir/../../..',
                     b'/test/././latest/dir/../../..',
                     b'/test/.//./latest/dir/../../..',
                     b'/test//.//.//latest/dir/../../..'
                     b'/test//./latest/dir/../../..'):
            wvstart('resolve: ' + path_msg(path))
            vfs.clear_cache()
            res = resolve(path)
            wvpasseq(((b'', vfs._root),), res)

        wvstart('resolve: /.tag')
        vfs.clear_cache()
        res = resolve(b'/.tag')
        wvpasseq(2, len(res))
        wvpasseq(((b'', vfs._root), (b'.tag', vfs._tags)),
                 res)
        ignore, tag_item = res[1]
        tag_content = frozenset(vfs.contents(repo, tag_item))
        wvpasseq(frozenset([(b'.', tag_item),
                            (b'test-tag', expected_test_tag_item)]),
                 tag_content)

        wvstart('resolve: /test')
        vfs.clear_cache()
        res = resolve(b'/test')
        wvpasseq(2, len(res))
        wvpasseq(((b'', vfs._root), (b'test', test_revlist_w_meta)), res)
        ignore, test_item = res[1]
        test_content = frozenset(vfs.contents(repo, test_item))
        # latest has metadata here due to caching
        wvpasseq(frozenset([(b'.', test_revlist_w_meta),
                            (save_time_str, expected_latest_item_w_meta),
                            (b'latest', expected_latest_link)]),
                 test_content)

        wvstart('resolve: /test/latest')
        vfs.clear_cache()
        res = resolve(b'/test/latest')
        wvpasseq(3, len(res))
        expected_latest_item_w_meta = vfs.Commit(meta=tip_tree[b'.'].meta,
                                                 oid=tip_tree_oid,
                                                 coid=tip_oid)
        expected = ((b'', vfs._root),
                    (b'test', test_revlist_w_meta),
                    (save_time_str, expected_latest_item_w_meta))
        wvpasseq(expected, res)
        ignore, latest_item = res[2]
        latest_content = frozenset(vfs.contents(repo, latest_item))
        expected = frozenset((x.name, vfs.Item(oid=x.oid, meta=x.meta))
                             for x in (tip_tree[name]
                                       for name in (b'.',
                                                    b'bad-symlink',
                                                    b'dir',
                                                    b'dir-symlink',
                                                    b'file',
                                                    b'file-symlink')))
        wvpasseq(expected, latest_content)

        wvstart('resolve: /test/latest/file')
        vfs.clear_cache()
        res = resolve(b'/test/latest/file')
        wvpasseq(4, len(res))
        expected_file_item_w_meta = vfs.Item(meta=tip_tree[b'file'].meta,
                                             oid=tip_tree[b'file'].oid)
        expected = ((b'', vfs._root),
                    (b'test', test_revlist_w_meta),
                    (save_time_str, expected_latest_item_w_meta),
                    (b'file', expected_file_item_w_meta))
        wvpasseq(expected, res)

        wvstart('resolve: /test/latest/bad-symlink')
        vfs.clear_cache()
        res = resolve(b'/test/latest/bad-symlink')
        wvpasseq(4, len(res))
        expected = ((b'', vfs._root),
                    (b'test', test_revlist_w_meta),
                    (save_time_str, expected_latest_item_w_meta),
                    (b'not-there', None))
        wvpasseq(expected, res)

        wvstart('resolve nofollow: /test/latest/bad-symlink')
        vfs.clear_cache()
        res = resolve(b'/test/latest/bad-symlink', follow=False)
        wvpasseq(4, len(res))
        bad_symlink_value = tip_tree[b'bad-symlink']
        expected_bad_symlink_item_w_meta = vfs.Item(meta=bad_symlink_value.meta,
                                                    oid=bad_symlink_value.oid)
        expected = ((b'', vfs._root),
                    (b'test', test_revlist_w_meta),
                    (save_time_str, expected_latest_item_w_meta),
                    (b'bad-symlink', expected_bad_symlink_item_w_meta))
        wvpasseq(expected, res)

        wvstart('resolve: /test/latest/file-symlink')
        vfs.clear_cache()
        res = resolve(b'/test/latest/file-symlink')
        wvpasseq(4, len(res))
        expected = ((b'', vfs._root),
                    (b'test', test_revlist_w_meta),
                    (save_time_str, expected_latest_item_w_meta),
                    (b'file', expected_file_item_w_meta))
        wvpasseq(expected, res)

        wvstart('resolve nofollow: /test/latest/file-symlink')
        vfs.clear_cache()
        res = resolve(b'/test/latest/file-symlink', follow=False)
        wvpasseq(4, len(res))
        file_symlink_value = tip_tree[b'file-symlink']
        expected_file_symlink_item_w_meta = vfs.Item(meta=file_symlink_value.meta,
                                                     oid=file_symlink_value.oid)
        expected = ((b'', vfs._root),
                    (b'test', test_revlist_w_meta),
                    (save_time_str, expected_latest_item_w_meta),
                    (b'file-symlink', expected_file_symlink_item_w_meta))
        wvpasseq(expected, res)

        wvstart('resolve: /test/latest/missing')
        vfs.clear_cache()
        res = resolve(b'/test/latest/missing')
        wvpasseq(4, len(res))
        name, item = res[-1]
        wvpasseq(b'missing', name)
        wvpass(item is None)

        for path in (b'/test/latest/file/',
                     b'/test/latest/file/.',
                     b'/test/latest/file/..',
                     b'/test/latest/file/../',
                     b'/test/latest/file/../.',
                     b'/test/latest/file/../..',
                     b'/test/latest/file/foo'):
            wvstart('resolve: ' + path_msg(path))
            vfs.clear_cache()
            try:
                resolve(path)
            except vfs.IOError as res_ex:
                wvpasseq(ENOTDIR, res_ex.errno)
                wvpasseq([b'', b'test', save_time_str, b'file'],
                         [name for name, item in res_ex.terminus])

        for path in (b'/test/latest/file-symlink/',
                     b'/test/latest/file-symlink/.',
                     b'/test/latest/file-symlink/..',
                     b'/test/latest/file-symlink/../',
                     b'/test/latest/file-symlink/../.',
                     b'/test/latest/file-symlink/../..'):
            wvstart('resolve nofollow: ' + path_msg(path))
            vfs.clear_cache()
            try:
                resolve(path, follow=False)
            except vfs.IOError as res_ex:
                wvpasseq(ENOTDIR, res_ex.errno)
                wvpasseq([b'', b'test', save_time_str, b'file'],
                         [name for name, item in res_ex.terminus])

        wvstart('resolve: non-directory parent')
        vfs.clear_cache()
        file_res = resolve(b'/test/latest/file')
        try:
            resolve(b'foo', parent=file_res)
        except vfs.IOError as res_ex:
            wvpasseq(ENOTDIR, res_ex.errno)
            wvpasseq(None, res_ex.terminus)

        wvstart('resolve nofollow: /test/latest/dir-symlink')
        vfs.clear_cache()
        res = resolve(b'/test/latest/dir-symlink', follow=False)
        wvpasseq(4, len(res))
        dir_symlink_value = tip_tree[b'dir-symlink']
        expected_dir_symlink_item_w_meta = vfs.Item(meta=dir_symlink_value.meta,
                                                     oid=dir_symlink_value.oid)
        expected = ((b'', vfs._root),
                    (b'test', test_revlist_w_meta),
                    (save_time_str, expected_latest_item_w_meta),
                    (b'dir-symlink', expected_dir_symlink_item_w_meta))
        wvpasseq(expected, res)

        dir_value = tip_tree[b'dir']
        expected_dir_item = vfs.Item(oid=dir_value.oid,
                                     meta=tree_dict(repo, dir_value.oid)[b'.'].meta)
        expected = ((b'', vfs._root),
                    (b'test', test_revlist_w_meta),
                    (save_time_str, expected_latest_item_w_meta),
                    (b'dir', expected_dir_item))
        def lresolve(*args, **keys):
            return resolve(*args, **dict(keys, follow=False))
        for resname, resolver in (('resolve', resolve),
                                  ('resolve nofollow', lresolve)):
            for path in (b'/test/latest/dir-symlink/',
                         b'/test/latest/dir-symlink/.'):
                wvstart(resname + ': ' + path_msg(path))
                vfs.clear_cache()
                res = resolver(path)
                wvpasseq(4, len(res))
                wvpasseq(expected, res)
        wvstart('resolve: /test/latest/dir-symlink')
        vfs.clear_cache()
        res = resolve(path)
        wvpasseq(4, len(res))
        wvpasseq(expected, res)

@wvtest
def test_local_resolve():
    prep_and_test_repo(b'local-vfs-resolve',
                       lambda x: LocalRepo(repo_dir=x), test_resolve)

@wvtest
def test_remote_resolve():
    prep_and_test_repo(b'remote-vfs-resolve',
                       lambda x: RemoteRepo(x), test_resolve)

def test_resolve_loop(repo, tmpdir):
    data_path = tmpdir + b'/src'
    os.mkdir(data_path)
    symlink(b'loop', data_path + b'/loop')
    ex((bup_path, b'init'))
    ex((bup_path, b'index', b'-v', data_path))
    save_utc = 100000
    ex((bup_path, b'save', b'-d', b'%d' % save_utc, b'-tvvn', b'test', b'--strip',
        data_path))
    save_name = strftime('%Y-%m-%d-%H%M%S', localtime(save_utc)).encode('ascii')
    try:
        wvpasseq('this call should never return',
                 repo.resolve(b'/test/%s/loop' % save_name))
    except vfs.IOError as res_ex:
        wvpasseq(ELOOP, res_ex.errno)
        wvpasseq([b'', b'test', save_name, b'loop'],
                 [name for name, item in res_ex.terminus])

@wvtest
def test_local_resolve_loop():
    prep_and_test_repo(b'local-vfs-resolve-loop',
                       lambda x: LocalRepo(x), test_resolve_loop)

@wvtest
def test_remote_resolve_loop():
    prep_and_test_repo(b'remote-vfs-resolve-loop',
                       lambda x: RemoteRepo(x), test_resolve_loop)

# FIXME: add tests for the want_meta=False cases.
