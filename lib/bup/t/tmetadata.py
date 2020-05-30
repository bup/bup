
from __future__ import absolute_import, print_function
import errno, glob, grp, pwd, stat, tempfile, subprocess

from wvtest import *

from bup import git, metadata
from bup import vfs
from bup.compat import range
from bup.helpers import clear_errors, detect_fakeroot, is_superuser, resolve_parent
from bup.repo import LocalRepo
from bup.xstat import utime, lutime
from buptest import no_lingering_errors, test_tempdir
import bup.helpers as helpers


top_dir = b'../../..'
bup_tmp = os.path.realpath(b'../../../t/tmp')
bup_path = top_dir + b'/bup'
start_dir = os.getcwd()


def ex(*cmd):
    try:
        cmd_str = b' '.join(cmd)
        print(cmd_str, file=sys.stderr)
        rc = subprocess.call(cmd)
        if rc < 0:
            print('terminated by signal', - rc, file=sys.stderr)
            sys.exit(1)
        elif rc > 0:
            print('returned exit status', rc, file=sys.stderr)
            sys.exit(1)
    except OSError as e:
        print('subprocess call failed:', e, file=sys.stderr)
        sys.exit(1)


def setup_testfs():
    assert(sys.platform.startswith('linux'))
    # Set up testfs with user_xattr, etc.
    if subprocess.call([b'modprobe', b'loop']) != 0:
        return False
    subprocess.call([b'umount', b'testfs'])
    ex(b'dd', b'if=/dev/zero', b'of=testfs.img', b'bs=1M', b'count=32')
    ex(b'mke2fs', b'-F', b'-j', b'-m', b'0', b'testfs.img')
    ex(b'rm', b'-rf', b'testfs')
    os.mkdir(b'testfs')
    ex(b'mount', b'-o', b'loop,acl,user_xattr', b'testfs.img', b'testfs')
    # Hide, so that tests can't create risks.
    os.chown(b'testfs', 0, 0)
    os.chmod(b'testfs', 0o700)
    return True


def cleanup_testfs():
    subprocess.call([b'umount', b'testfs'])
    helpers.unlink(b'testfs.img')


@wvtest
def test_clean_up_archive_path():
    with no_lingering_errors():
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


@wvtest
def test_risky_path():
    with no_lingering_errors():
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


@wvtest
def test_clean_up_extract_path():
    with no_lingering_errors():
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


@wvtest
def test_metadata_method():
    with no_lingering_errors():
        with test_tempdir(b'bup-tmetadata-') as tmpdir:
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
            repo = LocalRepo()
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


@wvtest
def test_from_path_error():
    if is_superuser() or detect_fakeroot():
        return
    with no_lingering_errors():
        with test_tempdir(b'bup-tmetadata-') as tmpdir:
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
                WVPASS(errmsg.startswith('read Linux attr'))
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
        else:
            raise
    return True


@wvtest
def test_apply_to_path_restricted_access():
    if is_superuser() or detect_fakeroot():
        return
    if sys.platform.startswith('cygwin'):
        return # chmod 000 isn't effective.
    with no_lingering_errors():
        with test_tempdir(b'bup-tmetadata-') as tmpdir:
            parent = tmpdir + b'/foo'
            path = parent + b'/bar'
            os.mkdir(parent)
            os.mkdir(path)
            clear_errors()
            m = metadata.from_path(path, archive_path=path, save_symlinks=True)
            WVPASSEQ(m.path, path)
            os.chmod(parent, 0o000)
            m.apply_to_path(path)
            print('saved_errors:', helpers.saved_errors, file=sys.stderr)
            expected_errors = ['utime: ']
            if m.linux_attr and _linux_attr_supported(tmpdir):
                expected_errors.append('Linux chattr: ')
            if metadata.xattr and m.linux_xattr:
                expected_errors.append("xattr.set '")
            WVPASS(len(helpers.saved_errors) == len(expected_errors))
            for i in range(len(expected_errors)):
                WVPASS(str(helpers.saved_errors[i]).startswith(expected_errors[i]))
            clear_errors()


@wvtest
def test_restore_over_existing_target():
    with no_lingering_errors():
        with test_tempdir(b'bup-tmetadata-') as tmpdir:
            path = tmpdir + b'/foo'
            os.mkdir(path)
            dir_m = metadata.from_path(path, archive_path=path, save_symlinks=True)
            os.rmdir(path)
            open(path, 'w').close()
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
            open(path + b'/bar', 'w').close()
            WVEXCEPT(Exception, file_m.create_path, path, create_symlinks=True)
            # Restore dir over non-empty dir.
            os.remove(path + b'/bar')
            os.mkdir(path + b'/bar')
            WVEXCEPT(Exception, dir_m.create_path, path, create_symlinks=True)


from bup.metadata import read_acl
if not read_acl:
    @wvtest
    def POSIX1E_ACL_SUPPORT_IS_MISSING():
        pass


from bup.metadata import xattr
if xattr:
    def remove_selinux(attrs):
        return list(filter(lambda i: not i in (b'security.selinux', ),
                           attrs))

    @wvtest
    def test_handling_of_incorrect_existing_linux_xattrs():
        if not is_superuser() or detect_fakeroot():
            WVMSG('skipping test -- not superuser')
            return
        if not setup_testfs():
            WVMSG('unable to load loop module; skipping dependent tests')
            return
        for f in glob.glob(b'testfs/*'):
            ex(b'rm', b'-rf', f)
        path = b'testfs/foo'
        open(path, 'w').close()
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
        os.chdir(start_dir)
        cleanup_testfs()
