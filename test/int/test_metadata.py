
import errno, stat, subprocess
import os, sys
import pytest

from buptest import exc
from wvpytest import *
import buptest

from bup import git, helpers, metadata
from bup import vfs
from bup.compat import fsencode
from bup.helpers import clear_errors, detect_fakeroot, is_superuser, resolve_parent
from bup.metadata import xattr
from bup.repo import LocalRepo
from bup.xstat import utime, lutime

lib_t_dir = os.path.dirname(fsencode(__file__))

top_dir = os.path.realpath(os.path.join(lib_t_dir, b'..', b'..'))

bup_path = top_dir + b'/bup'


def ex(*args, **kwargs):
    return buptest.exc(args, **kwargs)


def setup_testfs(img_path, mount_path, mb=32):
    # Try to set up testfs with user_xattr, etc.
    assert sys.platform.startswith('linux')
    with open(img_path, 'xb') as img:
        img.truncate(1024 * 1024 * mb)
    ex(b'mke2fs', b'-F', b'-j', b'-m', b'0', img_path)
    os.mkdir(mount_path)
    exr = ex(b'mount', b'-o', b'loop,acl,user_xattr', img_path, mount_path,
             check=False)
    if exr.rc != 0:
        return False
    # Hide, so that tests can't create risks.
    os.chown(b'testfs', 0, 0)
    os.chmod(b'testfs', 0o700)
    return True


def cleanup_testfs(img_path, mount_path):
    subprocess.call((b'umount', mount_path))
    helpers.unlink(img_path)


def test_clean_up_archive_path():
    cleanup = metadata._clean_up_path_for_archive
    WVPASSEQ(cleanup(b'foo'), b'foo')
    WVPASSEQ(cleanup(b'/foo'), b'foo')
    WVPASSEQ(cleanup(b'///foo'), b'foo')
    WVPASSEQ(cleanup(b'/foo/bar'), b'foo/bar')
    WVPASSEQ(cleanup(b'foo/./bar'), b'foo/bar')
    WVPASSEQ(cleanup(b'/foo/./bar'), b'foo/bar')
    WVPASSEQ(cleanup(b'/foo/./bar/././baz'), b'foo/bar/baz')
    WVPASSEQ(cleanup(b'/foo/./bar///././baz'), b'foo/bar/baz')
    WVPASSEQ(cleanup(b'//./foo/./bar///././baz/.///'), b'foo/bar/baz/')
    WVPASSEQ(cleanup(b'./foo/./.bar'), b'foo/.bar')
    WVPASSEQ(cleanup(b'./foo/.'), b'foo')
    WVPASSEQ(cleanup(b'./foo/..'), b'.')
    WVPASSEQ(cleanup(b'//./..//.../..//.'), b'.')
    WVPASSEQ(cleanup(b'//./..//..././/.'), b'...')
    WVPASSEQ(cleanup(b'/////.'), b'.')
    WVPASSEQ(cleanup(b'/../'), b'.')
    WVPASSEQ(cleanup(b''), b'.')


def test_risky_path():
    risky = metadata._risky_path
    WVPASS(risky(b'/foo'))
    WVPASS(risky(b'///foo'))
    WVPASS(risky(b'/../foo'))
    WVPASS(risky(b'../foo'))
    WVPASS(risky(b'foo/..'))
    WVPASS(risky(b'foo/../'))
    WVPASS(risky(b'foo/../bar'))
    WVFAIL(risky(b'foo'))
    WVFAIL(risky(b'foo/'))
    WVFAIL(risky(b'foo///'))
    WVFAIL(risky(b'./foo'))
    WVFAIL(risky(b'foo/.'))
    WVFAIL(risky(b'./foo/.'))
    WVFAIL(risky(b'foo/bar'))
    WVFAIL(risky(b'foo/./bar'))


def test_clean_up_extract_path():
    cleanup = metadata._clean_up_extract_path
    WVPASSEQ(cleanup(b'/foo'), b'foo')
    WVPASSEQ(cleanup(b'///foo'), b'foo')
    WVFAIL(cleanup(b'/../foo'))
    WVFAIL(cleanup(b'../foo'))
    WVFAIL(cleanup(b'foo/..'))
    WVFAIL(cleanup(b'foo/../'))
    WVFAIL(cleanup(b'foo/../bar'))
    WVPASSEQ(cleanup(b'foo'), b'foo')
    WVPASSEQ(cleanup(b'foo/'), b'foo/')
    WVPASSEQ(cleanup(b'foo///'), b'foo///')
    WVPASSEQ(cleanup(b'./foo'), b'./foo')
    WVPASSEQ(cleanup(b'foo/.'), b'foo/.')
    WVPASSEQ(cleanup(b'./foo/.'), b'./foo/.')
    WVPASSEQ(cleanup(b'foo/bar'), b'foo/bar')
    WVPASSEQ(cleanup(b'foo/./bar'), b'foo/./bar')
    WVPASSEQ(cleanup(b'/'), b'.')
    WVPASSEQ(cleanup(b'./'), b'./')
    WVPASSEQ(cleanup(b'///foo/bar'), b'foo/bar')
    WVPASSEQ(cleanup(b'///foo/bar'), b'foo/bar')


def test_metadata_method(tmpdir):
    bup_dir = tmpdir + b'/bup'
    data_path = tmpdir + b'/foo'
    os.mkdir(data_path)
    ex(b'touch', data_path + b'/file')
    ex(b'ln', b'-s', b'file', data_path + b'/symlink')
    test_time1 = 13 * 1000000000
    test_time2 = 42 * 1000000000
    utime(data_path + b'/file', (0, test_time1))
    lutime(data_path + b'/symlink', (0, 0))
    utime(data_path, (0, test_time2))
    ex(bup_path, b'-d', bup_dir, b'init')
    ex(bup_path, b'-d', bup_dir, b'index', b'-v', data_path)
    ex(bup_path, b'-d', bup_dir, b'save', b'-tvvn', b'test', data_path)
    git.check_repo_or_die(bup_dir)
    with  LocalRepo() as repo:
        resolved = vfs.resolve(repo,
                               b'/test/latest' + resolve_parent(data_path),
                               follow=False)
        leaf_name, leaf_item = resolved[-1]
        m = leaf_item.meta
        WVPASS(m.mtime == test_time2)
        WVPASS(leaf_name == b'foo')
        contents = tuple(vfs.contents(repo, leaf_item))
        WVPASS(len(contents) == 3)
        WVPASSEQ(frozenset(name for name, item in contents),
                 frozenset((b'.', b'file', b'symlink')))
        for name, item in contents:
            if name == b'file':
                m = item.meta
                WVPASS(m.mtime == test_time1)
            elif name == b'symlink':
                m = item.meta
                WVPASSEQ(m.symlink_target, b'file')
                WVPASSEQ(m.size, 4)
                WVPASSEQ(m.mtime, 0)


def _first_err():
    if helpers.saved_errors:
        return str(helpers.saved_errors[0])
    return ''


def test_from_path_error(tmpdir):
    if is_superuser() or detect_fakeroot():
        return
    path = tmpdir + b'/foo'
    os.mkdir(path)
    m = metadata.from_path(path, archive_path=path, save_symlinks=True)
    WVPASSEQ(m.path, path)
    os.chmod(path, 0o000)
    metadata.from_path(path, archive_path=path, save_symlinks=True)
    if metadata.get_linux_file_attr:
        print('saved_errors:', helpers.saved_errors, file=sys.stderr)
        WVPASS(len(helpers.saved_errors) == 1)
        errmsg = _first_err()
        WVPASS(errmsg.startswith('error: attr read failed '))
        clear_errors()


def _linux_attr_supported(path):
    # Expects path to denote a regular file or a directory.
    if not metadata.get_linux_file_attr:
        return False
    try:
        metadata.get_linux_file_attr(path)
    except OSError as e:
        if e.errno in (errno.ENOTTY, errno.ENOSYS, errno.EOPNOTSUPP):
            return False
        raise
    return True


def test_apply_to_path_restricted_access(tmpdir):
    if is_superuser() or detect_fakeroot():
        return
    if sys.platform.startswith('cygwin'):
        return # chmod 000 isn't effective.
    try:
        parent = tmpdir + b'/foo'
        path = parent + b'/bar'
        os.mkdir(parent)
        os.mkdir(path)
        clear_errors()
        if metadata.xattr:
            try:
                metadata.xattr.set(path, b'user.buptest', b'bup')
            except IOError as e: # matches _apply_linux_xattr_rec
                if e.errno not in (errno.EPERM, errno.EOPNOTSUPP):
                    raise
                print("failed to set test xattr")
        m = metadata.from_path(path, archive_path=path, save_symlinks=True)
        WVPASSEQ(m.path, path)
        os.chmod(parent, 0o000)
        m.apply_to_path(path)
        print(b'saved_errors:', helpers.saved_errors, file=sys.stderr)
        expected_errors = ['error: utime ']
        if m.linux_attr and _linux_attr_supported(tmpdir):
            expected_errors.append('error: chattr(')
        if metadata.xattr and m.linux_xattr:
            expected_errors.append('error: xattr.set ')
        WVPASS(len(helpers.saved_errors) == len(expected_errors))
        for i, err in enumerate(expected_errors):
            assert str(helpers.saved_errors[i]).startswith(err)
    finally:
        clear_errors()


def test_restore_over_existing_target(tmpdir):
    path = tmpdir + b'/foo'
    os.mkdir(path)
    dir_m = metadata.from_path(path, archive_path=path, save_symlinks=True)
    os.rmdir(path)
    with open(path, 'wb'): pass
    file_m = metadata.from_path(path, archive_path=path, save_symlinks=True)
    # Restore dir over file.
    WVPASSEQ(dir_m.create_path(path, create_symlinks=True), None)
    WVPASS(stat.S_ISDIR(os.stat(path).st_mode))
    # Restore dir over dir.
    WVPASSEQ(dir_m.create_path(path, create_symlinks=True), None)
    WVPASS(stat.S_ISDIR(os.stat(path).st_mode))
    # Restore file over dir.
    WVPASSEQ(file_m.create_path(path, create_symlinks=True), None)
    WVPASS(stat.S_ISREG(os.stat(path).st_mode))
    # Restore file over file.
    WVPASSEQ(file_m.create_path(path, create_symlinks=True), None)
    WVPASS(stat.S_ISREG(os.stat(path).st_mode))
    # Restore file over non-empty dir.
    os.remove(path)
    os.mkdir(path)
    with open(path + b'/bar', 'wb'): pass
    WVEXCEPT(Exception, file_m.create_path, path, create_symlinks=True)
    # Restore dir over non-empty dir.
    os.remove(path + b'/bar')
    os.mkdir(path + b'/bar')
    WVEXCEPT(Exception, dir_m.create_path, path, create_symlinks=True)


if xattr:
    def remove_selinux(attrs):
        return list(filter(lambda i: not i in (b'security.selinux', ),
                           attrs))

    def test_handling_of_incorrect_existing_linux_xattrs(tmpdir):
        if not sys.platform.startswith('linux'):
            pytest.skip('skipping test -- not linux')
            return
        if not is_superuser() or detect_fakeroot():
            pytest.skip('skipping test -- not superuser')
            return
        os.chdir(tmpdir) # reverted by common_test_environment
        if not setup_testfs(b'testfs.img', b'testfs'):
            pytest.skip('unable to set up test fs; skipping dependent tests')
            return
        try:
            path = b'testfs/foo'
            with open(path, 'wb'): pass
            xattr.set(path, b'foo', b'bar', namespace=xattr.NS_USER)
            m = metadata.from_path(path, archive_path=path, save_symlinks=True)
            xattr.set(path, b'baz', b'bax', namespace=xattr.NS_USER)
            m.apply_to_path(path, restore_numeric_ids=False)
            WVPASSEQ(remove_selinux(xattr.list(path)), [b'user.foo'])
            WVPASSEQ(xattr.get(path, b'user.foo'), b'bar')
            xattr.set(path, b'foo', b'baz', namespace=xattr.NS_USER)
            m.apply_to_path(path, restore_numeric_ids=False)
            WVPASSEQ(remove_selinux(xattr.list(path)), [b'user.foo'])
            WVPASSEQ(xattr.get(path, b'user.foo'), b'bar')
            xattr.remove(path, b'foo', namespace=xattr.NS_USER)
            m.apply_to_path(path, restore_numeric_ids=False)
            WVPASSEQ(remove_selinux(xattr.list(path)), [b'user.foo'])
            WVPASSEQ(xattr.get(path, b'user.foo'), b'bar')
        finally:
            cleanup_testfs(b'testfs.img', b'testfs')


def test_maximal_metadata(tmpdir):
    # Currently just tests that the hash computation isn't broken
    if not sys.platform.startswith('linux'):
        pytest.skip('skipping test -- not linux')
        return
    if not is_superuser() or detect_fakeroot():
        pytest.skip('skipping test -- not superuser')
        return
    os.chdir(tmpdir) # reverted by common_test_environment
    if not setup_testfs(b'testfs.img', b'testfs'):
        pytest.skip('unable to set up test fs; skipping dependent tests')
        return
    try:
        os.chdir(b'testfs')
        with open('canary', 'wb') as f:
            f.write(b'something')
        try: # linux xattrs
            exc((b'attr', b'-s', b'foo', b'-V', b'bar', b'canary'))
        except FileNotFoundError:
            pass
        try: # posix1e acls
            exc((b'setfacl', '-m', 'u:root:r', b'canary'))
        except FileNotFoundError:
            pass
        try: # linux attrs
            exc((b'chattr', b'+acd', b'canary'))
        except FileNotFoundError:
            pass
        m = metadata.from_path(b'canary')
        # Check that __hash__ works properly
        assert isinstance(hash(m), int)
    finally:
        cleanup_testfs(b'testfs.img', b'testfs')
