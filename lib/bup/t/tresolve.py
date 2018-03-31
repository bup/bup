
from __future__ import absolute_import, print_function
from errno import ELOOP, ENOTDIR
from os import environ, symlink
from stat import S_IFDIR
from sys import stderr
from time import localtime, strftime

from wvtest import *

from bup import git, vfs
from bup.metadata import Metadata
from bup.repo import LocalRepo
from bup.test.vfs import tree_dict
from buptest import ex, exo, no_lingering_errors, test_tempdir

top_dir = '../../..'
bup_tmp = os.path.realpath('../../../t/tmp')
bup_path = top_dir + '/bup'
start_dir = os.getcwd()

## The clear_cache() calls below are to make sure that the test starts
## from a known state since at the moment the cache entry for a given
## item (like a commit) can change.  For example, its meta value might
## be promoted from a mode to a Metadata instance once the tree it
## refers to is traversed.

@wvtest
def test_resolve():
    with no_lingering_errors():
        with test_tempdir('bup-tvfs-') as tmpdir:
            resolve = vfs.resolve
            bup_dir = tmpdir + '/bup'
            environ['GIT_DIR'] = bup_dir
            environ['BUP_DIR'] = bup_dir
            git.repodir = bup_dir
            data_path = tmpdir + '/src'
            save_time = 100000
            save_time_str = strftime('%Y-%m-%d-%H%M%S', localtime(save_time))
            os.mkdir(data_path)
            os.mkdir(data_path + '/dir')
            with open(data_path + '/file', 'w+') as tmpfile:
                print('canary', file=tmpfile)
            symlink('file', data_path + '/file-symlink')
            symlink('dir', data_path + '/dir-symlink')
            symlink('not-there', data_path + '/bad-symlink')
            ex((bup_path, 'init'))
            ex((bup_path, 'index', '-v', data_path))
            ex((bup_path, 'save', '-d', str(save_time), '-tvvn', 'test',
                '--strip', data_path))
            ex((bup_path, 'tag', 'test-tag', 'test'))
            repo = LocalRepo()

            tip_hash = exo(('git', 'show-ref', 'refs/heads/test'))[0]
            tip_oidx = tip_hash.strip().split()[0]
            tip_oid = tip_oidx.decode('hex')
            tip_tree_oidx = exo(('git', 'log', '--pretty=%T', '-n1',
                                 tip_oidx))[0].strip()
            tip_tree_oid = tip_tree_oidx.decode('hex')
            tip_tree = tree_dict(repo, tip_tree_oid)
            test_revlist_w_meta = vfs.RevList(meta=tip_tree['.'].meta,
                                              oid=tip_oid)
            expected_latest_item = vfs.Commit(meta=S_IFDIR | 0o755,
                                              oid=tip_tree_oid,
                                              coid=tip_oid)
            expected_latest_item_w_meta = vfs.Commit(meta=tip_tree['.'].meta,
                                                     oid=tip_tree_oid,
                                                     coid=tip_oid)
            expected_latest_link = vfs.FakeLink(meta=vfs.default_symlink_mode,
                                                target=save_time_str)
            expected_test_tag_item = expected_latest_item

            wvstart('resolve: /')
            vfs.clear_cache()
            res = resolve(repo, '/')
            wvpasseq(1, len(res))
            wvpasseq((('', vfs._root),), res)
            ignore, root_item = res[0]
            root_content = frozenset(vfs.contents(repo, root_item))
            wvpasseq(frozenset([('.', root_item),
                                ('.tag', vfs._tags),
                                ('test', test_revlist_w_meta)]),
                     root_content)
            for path in ('//', '/.', '/./', '/..', '/../',
                         '/test/latest/dir/../../..',
                         '/test/latest/dir/../../../',
                         '/test/latest/dir/../../../.',
                         '/test/latest/dir/../../..//',
                         '/test//latest/dir/../../..',
                         '/test/./latest/dir/../../..',
                         '/test/././latest/dir/../../..',
                         '/test/.//./latest/dir/../../..',
                         '/test//.//.//latest/dir/../../..'
                         '/test//./latest/dir/../../..'):
                wvstart('resolve: ' + path)
                vfs.clear_cache()
                res = resolve(repo, path)
                wvpasseq((('', vfs._root),), res)

            wvstart('resolve: /.tag')
            vfs.clear_cache()
            res = resolve(repo, '/.tag')
            wvpasseq(2, len(res))
            wvpasseq((('', vfs._root), ('.tag', vfs._tags)),
                     res)
            ignore, tag_item = res[1]
            tag_content = frozenset(vfs.contents(repo, tag_item))
            wvpasseq(frozenset([('.', tag_item),
                                ('test-tag', expected_test_tag_item)]),
                     tag_content)

            wvstart('resolve: /test')
            vfs.clear_cache()
            res = resolve(repo, '/test')
            wvpasseq(2, len(res))
            wvpasseq((('', vfs._root), ('test', test_revlist_w_meta)), res)
            ignore, test_item = res[1]
            test_content = frozenset(vfs.contents(repo, test_item))
            # latest has metadata here due to caching
            wvpasseq(frozenset([('.', test_revlist_w_meta),
                                (save_time_str, expected_latest_item_w_meta),
                                ('latest', expected_latest_link)]),
                     test_content)

            wvstart('resolve: /test/latest')
            vfs.clear_cache()
            res = resolve(repo, '/test/latest')
            wvpasseq(3, len(res))
            expected_latest_item_w_meta = vfs.Commit(meta=tip_tree['.'].meta,
                                                     oid=tip_tree_oid,
                                                     coid=tip_oid)
            expected = (('', vfs._root),
                        ('test', test_revlist_w_meta),
                        (save_time_str, expected_latest_item_w_meta))
            wvpasseq(expected, res)
            ignore, latest_item = res[2]
            latest_content = frozenset(vfs.contents(repo, latest_item))
            expected = frozenset((x.name, vfs.Item(oid=x.oid, meta=x.meta))
                                 for x in (tip_tree[name]
                                           for name in ('.',
                                                        'bad-symlink',
                                                        'dir',
                                                        'dir-symlink',
                                                        'file',
                                                        'file-symlink')))
            wvpasseq(expected, latest_content)

            wvstart('resolve: /test/latest/file')
            vfs.clear_cache()
            res = resolve(repo, '/test/latest/file')
            wvpasseq(4, len(res))
            expected_file_item_w_meta = vfs.Item(meta=tip_tree['file'].meta,
                                                 oid=tip_tree['file'].oid)
            expected = (('', vfs._root),
                        ('test', test_revlist_w_meta),
                        (save_time_str, expected_latest_item_w_meta),
                        ('file', expected_file_item_w_meta))
            wvpasseq(expected, res)

            wvstart('resolve: /test/latest/bad-symlink')
            vfs.clear_cache()
            res = resolve(repo, '/test/latest/bad-symlink')
            wvpasseq(4, len(res))
            expected = (('', vfs._root),
                        ('test', test_revlist_w_meta),
                        (save_time_str, expected_latest_item_w_meta),
                        ('not-there', None))
            wvpasseq(expected, res)

            wvstart('resolve nofollow: /test/latest/bad-symlink')
            vfs.clear_cache()
            res = resolve(repo, '/test/latest/bad-symlink', follow=False)
            wvpasseq(4, len(res))
            bad_symlink_value = tip_tree['bad-symlink']
            expected_bad_symlink_item_w_meta = vfs.Item(meta=bad_symlink_value.meta,
                                                        oid=bad_symlink_value.oid)
            expected = (('', vfs._root),
                        ('test', test_revlist_w_meta),
                        (save_time_str, expected_latest_item_w_meta),
                        ('bad-symlink', expected_bad_symlink_item_w_meta))
            wvpasseq(expected, res)

            wvstart('resolve: /test/latest/file-symlink')
            vfs.clear_cache()
            res = resolve(repo, '/test/latest/file-symlink')
            wvpasseq(4, len(res))
            expected = (('', vfs._root),
                        ('test', test_revlist_w_meta),
                        (save_time_str, expected_latest_item_w_meta),
                        ('file', expected_file_item_w_meta))
            wvpasseq(expected, res)

            wvstart('resolve nofollow: /test/latest/file-symlink')
            vfs.clear_cache()
            res = resolve(repo, '/test/latest/file-symlink', follow=False)
            wvpasseq(4, len(res))
            file_symlink_value = tip_tree['file-symlink']
            expected_file_symlink_item_w_meta = vfs.Item(meta=file_symlink_value.meta,
                                                         oid=file_symlink_value.oid)
            expected = (('', vfs._root),
                        ('test', test_revlist_w_meta),
                        (save_time_str, expected_latest_item_w_meta),
                        ('file-symlink', expected_file_symlink_item_w_meta))
            wvpasseq(expected, res)

            wvstart('resolve: /test/latest/missing')
            vfs.clear_cache()
            res = resolve(repo, '/test/latest/missing')
            wvpasseq(4, len(res))
            name, item = res[-1]
            wvpasseq('missing', name)
            wvpass(item is None)

            for path in ('/test/latest/file/',
                         '/test/latest/file/.',
                         '/test/latest/file/..',
                         '/test/latest/file/../',
                         '/test/latest/file/../.',
                         '/test/latest/file/../..',
                         '/test/latest/file/foo'):
                wvstart('resolve: ' + path)
                vfs.clear_cache()
                try:
                    resolve(repo, path)
                except vfs.IOError as res_ex:
                    wvpasseq(ENOTDIR, res_ex.errno)
                    wvpasseq(['', 'test', save_time_str, 'file'],
                             [name for name, item in res_ex.terminus])

            for path in ('/test/latest/file-symlink/',
                         '/test/latest/file-symlink/.',
                         '/test/latest/file-symlink/..',
                         '/test/latest/file-symlink/../',
                         '/test/latest/file-symlink/../.',
                         '/test/latest/file-symlink/../..'):
                wvstart('resolve nofollow: ' + path)
                vfs.clear_cache()
                try:
                    resolve(repo, path, follow=False)
                except vfs.IOError as res_ex:
                    wvpasseq(ENOTDIR, res_ex.errno)
                    wvpasseq(['', 'test', save_time_str, 'file'],
                             [name for name, item in res_ex.terminus])

            wvstart('resolve: non-directory parent')
            vfs.clear_cache()
            file_res = resolve(repo, '/test/latest/file')
            try:
                resolve(repo, 'foo', parent=file_res)
            except vfs.IOError as res_ex:
                wvpasseq(ENOTDIR, res_ex.errno)
                wvpasseq(None, res_ex.terminus)

            wvstart('resolve nofollow: /test/latest/dir-symlink')
            vfs.clear_cache()
            res = resolve(repo, '/test/latest/dir-symlink', follow=False)
            wvpasseq(4, len(res))
            dir_symlink_value = tip_tree['dir-symlink']
            expected_dir_symlink_item_w_meta = vfs.Item(meta=dir_symlink_value.meta,
                                                         oid=dir_symlink_value.oid)
            expected = (('', vfs._root),
                        ('test', test_revlist_w_meta),
                        (save_time_str, expected_latest_item_w_meta),
                        ('dir-symlink', expected_dir_symlink_item_w_meta))
            wvpasseq(expected, res)

            dir_value = tip_tree['dir']
            expected_dir_item = vfs.Item(oid=dir_value.oid,
                                         meta=tree_dict(repo, dir_value.oid)['.'].meta)
            expected = (('', vfs._root),
                        ('test', test_revlist_w_meta),
                        (save_time_str, expected_latest_item_w_meta),
                        ('dir', expected_dir_item))
            def lresolve(*args, **keys):
                return resolve(*args, **dict(keys, follow=False))
            for resname, resolver in (('resolve', resolve),
                                      ('resolve nofollow', lresolve)):
                for path in ('/test/latest/dir-symlink/',
                             '/test/latest/dir-symlink/.'):
                    wvstart(resname + ': ' + path)
                    vfs.clear_cache()
                    res = resolver(repo, path)
                    wvpasseq(4, len(res))
                    wvpasseq(expected, res)
            wvstart('resolve: /test/latest/dir-symlink')
            vfs.clear_cache()
            res = resolve(repo, path)
            wvpasseq(4, len(res))
            wvpasseq(expected, res)

@wvtest
def test_resolve_loop():
    with no_lingering_errors():
        with test_tempdir('bup-tvfs-resloop-') as tmpdir:
            resolve = vfs.resolve
            bup_dir = tmpdir + '/bup'
            environ['GIT_DIR'] = bup_dir
            environ['BUP_DIR'] = bup_dir
            git.repodir = bup_dir
            repo = LocalRepo()
            data_path = tmpdir + '/src'
            os.mkdir(data_path)
            symlink('loop', data_path + '/loop')
            ex((bup_path, 'init'))
            ex((bup_path, 'index', '-v', data_path))
            save_utc = 100000
            ex((bup_path, 'save', '-d', str(save_utc), '-tvvn', 'test', '--strip',
                data_path))
            save_name = strftime('%Y-%m-%d-%H%M%S', localtime(save_utc))
            try:
                wvpasseq('this call should never return',
                         resolve(repo, '/test/%s/loop' % save_name))
            except vfs.IOError as res_ex:
                wvpasseq(ELOOP, res_ex.errno)
                wvpasseq(['', 'test', save_name, 'loop'],
                         [name for name, item in res_ex.terminus])

# FIXME: add tests for the want_meta=False cases.
