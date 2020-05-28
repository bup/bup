
from __future__ import absolute_import, print_function
from binascii import unhexlify
from collections import namedtuple
from errno import ELOOP, ENOTDIR
from io import BytesIO
from os import symlink
from random import Random, randint
from stat import S_IFDIR, S_IFLNK, S_IFREG, S_ISDIR, S_ISREG
from sys import stderr
import os
import sys
from time import localtime, strftime, tzset

from wvpytest import *

from bup._helpers import write_random
from bup import git, metadata, vfs
from bup.compat import environ, fsencode, items, range
from bup.git import BUP_CHUNKED
from bup.helpers import exc, shstr
from bup.metadata import Metadata
from bup.repo import LocalRepo
from buptest import ex, exo
from buptest.vfs import tree_dict

lib_t_dir = os.path.dirname(fsencode(__file__))
top_dir = os.path.join(lib_t_dir, b'../..')
bup_path = top_dir + b'/bup'

def ex(cmd, **kwargs):
    print(shstr(cmd), file=stderr)
    return exc(cmd, **kwargs)

def test_default_modes():
    wvpasseq(S_IFREG | 0o644, vfs.default_file_mode)
    wvpasseq(S_IFDIR | 0o755, vfs.default_dir_mode)
    wvpasseq(S_IFLNK | 0o755, vfs.default_symlink_mode)

def test_cache_behavior():
    orig_max = vfs._cache_max_items
    try:
        vfs._cache_max_items = 2
        vfs.clear_cache()
        wvpasseq({}, vfs._cache)
        wvpasseq([], vfs._cache_keys)
        wvfail(vfs._cache_keys)
        wvexcept(Exception, vfs.cache_notice, b'x', 1)
        key_0 = b'itm:' + b'\0' * 20
        key_1 = b'itm:' + b'\1' * 20
        key_2 = b'itm:' + b'\2' * 20
        vfs.cache_notice(key_0, b'something')
        wvpasseq({key_0 : b'something'}, vfs._cache)
        wvpasseq([key_0], vfs._cache_keys)
        vfs.cache_notice(key_1, b'something else')
        wvpasseq({key_0 : b'something', key_1 : b'something else'}, vfs._cache)
        wvpasseq(frozenset([key_0, key_1]), frozenset(vfs._cache_keys))
        vfs.cache_notice(key_2, b'and also')
        wvpasseq(2, len(vfs._cache))
        wvpass(frozenset(items(vfs._cache))
               < frozenset(items({key_0 : b'something',
                                  key_1 : b'something else',
                                  key_2 : b'and also'})))
        wvpasseq(2, len(vfs._cache_keys))
        wvpass(frozenset(vfs._cache_keys) < frozenset([key_0, key_1, key_2]))
        vfs.clear_cache()
        wvpasseq({}, vfs._cache)
        wvpasseq([], vfs._cache_keys)
    finally:
        vfs._cache_max_items = orig_max
        vfs.clear_cache()

## The clear_cache() calls below are to make sure that the test starts
## from a known state since at the moment the cache entry for a given
## item (like a commit) can change.  For example, its meta value might
## be promoted from a mode to a Metadata instance once the tree it
## refers to is traversed.

def run_augment_item_meta_tests(repo,
                                file_path, file_size,
                                link_path, link_target):
    _, file_item = vfs.resolve(repo, file_path)[-1]
    _, link_item = vfs.resolve(repo, link_path, follow=False)[-1]
    wvpass(isinstance(file_item.meta, Metadata))
    wvpass(isinstance(link_item.meta, Metadata))
    # Note: normally, modifying item.meta values is forbidden
    file_item.meta.size = file_item.meta.size or vfs.item_size(repo, file_item)
    link_item.meta.size = link_item.meta.size or vfs.item_size(repo, link_item)

    ## Ensure a fully populated item is left alone
    augmented = vfs.augment_item_meta(repo, file_item)
    wvpass(augmented is file_item)
    wvpass(augmented.meta is file_item.meta)
    augmented = vfs.augment_item_meta(repo, file_item, include_size=True)
    wvpass(augmented is file_item)
    wvpass(augmented.meta is file_item.meta)

    ## Ensure a missing size is handled poperly
    file_item.meta.size = None
    augmented = vfs.augment_item_meta(repo, file_item)
    wvpass(augmented is file_item)
    wvpass(augmented.meta is file_item.meta)
    augmented = vfs.augment_item_meta(repo, file_item, include_size=True)
    wvpass(augmented is not file_item)
    wvpasseq(file_size, augmented.meta.size)

    ## Ensure a meta mode is handled properly
    mode_item = file_item._replace(meta=vfs.default_file_mode)
    augmented = vfs.augment_item_meta(repo, mode_item)
    augmented_w_size = vfs.augment_item_meta(repo, mode_item, include_size=True)
    for item in (augmented, augmented_w_size):
        meta = item.meta
        wvpass(item is not file_item)
        wvpass(isinstance(meta, Metadata))
        wvpasseq(vfs.default_file_mode, meta.mode)
        wvpasseq((None, None, 0, 0, 0),
                 (meta.uid, meta.gid, meta.atime, meta.mtime, meta.ctime))
    wvpass(augmented.meta.size is None)
    wvpasseq(file_size, augmented_w_size.meta.size)

    ## Ensure symlinks are handled properly
    mode_item = link_item._replace(meta=vfs.default_symlink_mode)
    augmented = vfs.augment_item_meta(repo, mode_item)
    wvpass(augmented is not mode_item)
    wvpass(isinstance(augmented.meta, Metadata))
    wvpasseq(link_target, augmented.meta.symlink_target)
    wvpasseq(len(link_target), augmented.meta.size)
    augmented = vfs.augment_item_meta(repo, mode_item, include_size=True)
    wvpass(augmented is not mode_item)
    wvpass(isinstance(augmented.meta, Metadata))
    wvpasseq(link_target, augmented.meta.symlink_target)
    wvpasseq(len(link_target), augmented.meta.size)


def test_item_mode():
    mode = S_IFDIR | 0o755
    meta = metadata.from_path(b'.')
    oid = b'\0' * 20
    wvpasseq(mode, vfs.item_mode(vfs.Item(oid=oid, meta=mode)))
    wvpasseq(meta.mode, vfs.item_mode(vfs.Item(oid=oid, meta=meta)))

def test_reverse_suffix_duplicates():
    suffix = lambda x: tuple(vfs._reverse_suffix_duplicates(x))
    wvpasseq((b'x',), suffix((b'x',)))
    wvpasseq((b'x', b'y'), suffix((b'x', b'y')))
    wvpasseq((b'x-1', b'x-0'), suffix((b'x',) * 2))
    wvpasseq([b'x-%02d' % n for n in reversed(range(11))],
             list(suffix((b'x',) * 11)))
    wvpasseq((b'x-1', b'x-0', b'y'), suffix((b'x', b'x', b'y')))
    wvpasseq((b'x', b'y-1', b'y-0'), suffix((b'x', b'y', b'y')))
    wvpasseq((b'x', b'y-1', b'y-0', b'z'), suffix((b'x', b'y', b'y', b'z')))

def test_misc(tmpdir):
    bup_dir = tmpdir + b'/bup'
    environ[b'GIT_DIR'] = bup_dir
    environ[b'BUP_DIR'] = bup_dir
    git.repodir = bup_dir
    data_path = tmpdir + b'/src'
    os.mkdir(data_path)
    with open(data_path + b'/file', 'wb+') as tmpfile:
        tmpfile.write(b'canary\n')
    symlink(b'file', data_path + b'/symlink')
    ex((bup_path, b'init'))
    ex((bup_path, b'index', b'-v', data_path))
    ex((bup_path, b'save', b'-d', b'100000', b'-tvvn', b'test',
        b'--strip', data_path))
    repo = LocalRepo()

    ls_tree = exo((b'git', b'ls-tree', b'test', b'symlink')).out
    mode, typ, oidx, name = ls_tree.strip().split(None, 3)
    assert name == b'symlink'
    link_item = vfs.Item(oid=unhexlify(oidx), meta=int(mode, 8))
    wvpasseq(b'file', vfs.readlink(repo, link_item))

    ls_tree = exo((b'git', b'ls-tree', b'test', b'file')).out
    mode, typ, oidx, name = ls_tree.strip().split(None, 3)
    assert name == b'file'
    file_item = vfs.Item(oid=unhexlify(oidx), meta=int(mode, 8))
    wvexcept(Exception, vfs.readlink, repo, file_item)

    wvpasseq(4, vfs.item_size(repo, link_item))
    wvpasseq(7, vfs.item_size(repo, file_item))
    meta = metadata.from_path(fsencode(__file__))
    meta.size = 42
    fake_item = file_item._replace(meta=meta)
    wvpasseq(42, vfs.item_size(repo, fake_item))

    _, fakelink_item = vfs.resolve(repo, b'/test/latest', follow=False)[-1]
    wvpasseq(17, vfs.item_size(repo, fakelink_item))

    run_augment_item_meta_tests(repo,
                                b'/test/latest/file', 7,
                                b'/test/latest/symlink', b'file')

    # FIXME: this caused StopIteration
    #_, file_item = vfs.resolve(repo, '/file')[-1]
    _, file_item = vfs.resolve(repo, b'/test/latest/file')[-1]
    file_copy = vfs.copy_item(file_item)
    wvpass(file_copy is not file_item)
    wvpass(file_copy.meta is not file_item.meta)
    wvpass(isinstance(file_copy, tuple))
    wvpass(file_item.meta.user)
    wvpass(file_copy.meta.user)
    file_copy.meta.user = None
    wvpass(file_item.meta.user)

def write_sized_random_content(parent_dir, size, seed):
    verbose = 0
    with open(b'%s/%d' % (parent_dir, size), 'wb') as f:
        write_random(f.fileno(), size, seed, verbose)

def validate_vfs_streaming_read(repo, item, expected_path, read_sizes):
    for read_size in read_sizes:
        with open(expected_path, 'rb') as expected:
            with vfs.fopen(repo, item) as actual:
                ex_buf = expected.read(read_size)
                act_buf = actual.read(read_size)
                while ex_buf and act_buf:
                    wvpassge(read_size, len(ex_buf))
                    wvpassge(read_size, len(act_buf))
                    wvpasseq(len(ex_buf), len(act_buf))
                    wvpass(ex_buf == act_buf)
                    ex_buf = expected.read(read_size)
                    act_buf = actual.read(read_size)
                wvpasseq(b'', ex_buf)
                wvpasseq(b'', act_buf)

def validate_vfs_seeking_read(repo, item, expected_path, read_sizes):
    def read_act(act_pos):
        with vfs.fopen(repo, item) as actual:
            actual.seek(act_pos)
            wvpasseq(act_pos, actual.tell())
            act_buf = actual.read(read_size)
            act_pos += len(act_buf)
            wvpasseq(act_pos, actual.tell())
            return act_pos, act_buf

    for read_size in read_sizes:
        with open(expected_path, 'rb') as expected:
                ex_buf = expected.read(read_size)
                act_buf = None
                act_pos = 0
                while ex_buf:
                    act_pos, act_buf = read_act(act_pos)
                    wvpassge(read_size, len(ex_buf))
                    wvpassge(read_size, len(act_buf))
                    wvpasseq(len(ex_buf), len(act_buf))
                    wvpass(ex_buf == act_buf)
                    if not act_buf:
                        break
                    ex_buf = expected.read(read_size)
                else:  # hit expected eof first
                    act_pos, act_buf = read_act(act_pos)
                wvpasseq(b'', ex_buf)
                wvpasseq(b'', act_buf)

def test_read_and_seek(tmpdir):
    # Write a set of randomly sized files containing random data whose
    # names are their sizes, and then verify that what we get back
    # from the vfs when seeking and reading with various block sizes
    # matches the original content.
    resolve = vfs.resolve
    bup_dir = tmpdir + b'/bup'
    environ[b'GIT_DIR'] = bup_dir
    environ[b'BUP_DIR'] = bup_dir
    git.repodir = bup_dir
    repo = LocalRepo()
    data_path = tmpdir + b'/src'
    os.mkdir(data_path)
    seed = randint(-(1 << 31), (1 << 31) - 1)
    rand = Random()
    rand.seed(seed)
    print('test_read seed:', seed, file=sys.stderr)
    max_size = 2 * 1024 * 1024
    sizes = set((rand.randint(1, max_size) for _ in range(5)))
    sizes.add(1)
    sizes.add(max_size)
    for size in sizes:
        write_sized_random_content(data_path, size, seed)
    ex((bup_path, b'init'))
    ex((bup_path, b'index', b'-v', data_path))
    ex((bup_path, b'save', b'-d', b'100000', b'-tvvn', b'test',
        b'--strip', data_path))
    read_sizes = set((rand.randint(1, max_size) for _ in range(10)))
    sizes.add(1)
    sizes.add(max_size)
    print('test_read src sizes:', sizes, file=sys.stderr)
    print('test_read read sizes:', read_sizes, file=sys.stderr)
    for size in sizes:
        res = resolve(repo, b'/test/latest/' + str(size).encode('ascii'))
        _, item = res[-1]
        wvpasseq(size, vfs.item_size(repo, res[-1][1]))
        validate_vfs_streaming_read(repo, item,
                                    b'%s/%d' % (data_path, size),
                                    read_sizes)
        validate_vfs_seeking_read(repo, item,
                                  b'%s/%d' % (data_path, size),
                                  read_sizes)

def test_contents_with_mismatched_bupm_git_ordering(tmpdir):
    bup_dir = tmpdir + b'/bup'
    environ[b'GIT_DIR'] = bup_dir
    environ[b'BUP_DIR'] = bup_dir
    git.repodir = bup_dir
    data_path = tmpdir + b'/src'
    os.mkdir(data_path)
    os.mkdir(data_path + b'/foo')
    with open(data_path + b'/foo.', 'wb+') as tmpfile:
        tmpfile.write(b'canary\n')
    ex((bup_path, b'init'))
    ex((bup_path, b'index', b'-v', data_path))
    save_utc = 100000
    save_name = strftime('%Y-%m-%d-%H%M%S', localtime(save_utc)).encode('ascii')
    ex((bup_path, b'save', b'-tvvn', b'test', b'-d', b'%d' % save_utc,
        b'--strip', data_path))
    repo = LocalRepo()
    tip_sref = exo((b'git', b'show-ref', b'refs/heads/test')).out
    tip_oidx = tip_sref.strip().split()[0]
    tip_tree_oidx = exo((b'git', b'log', b'--pretty=%T', b'-n1',
                         tip_oidx)).out.strip()
    tip_tree_oid = unhexlify(tip_tree_oidx)
    tip_tree = tree_dict(repo, tip_tree_oid)

    name, item = vfs.resolve(repo, b'/test/latest')[2]
    wvpasseq(save_name, name)
    expected = frozenset((x.name, vfs.Item(oid=x.oid, meta=x.meta))
                         for x in (tip_tree[name]
                                   for name in (b'.', b'foo', b'foo.')))
    contents = tuple(vfs.contents(repo, item))
    wvpasseq(expected, frozenset(contents))
    # Spot check, in case tree_dict shares too much code with the vfs
    name, item = next(((n, i) for n, i in contents if n == b'foo'))
    wvpass(S_ISDIR(item.meta))
    name, item = next(((n, i) for n, i in contents if n == b'foo.'))
    wvpass(S_ISREG(item.meta.mode))

def test_duplicate_save_dates(tmpdir):
    bup_dir = tmpdir + b'/bup'
    environ[b'GIT_DIR'] = bup_dir
    environ[b'BUP_DIR'] = bup_dir
    environ[b'TZ'] = b'UTC'
    tzset()
    git.repodir = bup_dir
    data_path = tmpdir + b'/src'
    os.mkdir(data_path)
    with open(data_path + b'/file', 'wb+') as tmpfile:
        tmpfile.write(b'canary\n')
    ex((b'env',))
    ex((bup_path, b'init'))
    ex((bup_path, b'index', b'-v', data_path))
    for i in range(11):
        ex((bup_path, b'save', b'-d', b'100000', b'-n', b'test',
            data_path))
    repo = LocalRepo()
    res = vfs.resolve(repo, b'/test')
    wvpasseq(2, len(res))
    name, revlist = res[-1]
    wvpasseq(b'test', name)
    wvpasseq((b'.',
              b'1970-01-02-034640-00',
              b'1970-01-02-034640-01',
              b'1970-01-02-034640-02',
              b'1970-01-02-034640-03',
              b'1970-01-02-034640-04',
              b'1970-01-02-034640-05',
              b'1970-01-02-034640-06',
              b'1970-01-02-034640-07',
              b'1970-01-02-034640-08',
              b'1970-01-02-034640-09',
              b'1970-01-02-034640-10',
              b'latest'),
             tuple(sorted(x[0] for x in vfs.contents(repo, revlist))))

def test_item_read_write():
    x = vfs.Root(meta=13)
    stream = BytesIO()
    vfs.write_item(stream, x)
    print('stream:', repr(stream.getvalue()), stream.tell(), file=sys.stderr)
    stream.seek(0)
    wvpasseq(x, vfs.read_item(stream))
