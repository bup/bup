import glob, grp, pwd, stat, tempfile, subprocess, xattr
import bup.helpers as helpers
from bup import metadata
from bup.helpers import clear_errors, detect_fakeroot
from wvtest import *


top_dir = os.getcwd()


def ex(*cmd):
    try:
        cmd_str = ' '.join(cmd)
        print >> sys.stderr, cmd_str
        rc = subprocess.call(cmd)
        if rc < 0:
            print >> sys.stderr, 'terminated by signal', - rc
            sys.exit(1)
        elif rc > 0:
            print >> sys.stderr, 'returned exit status', rc
            sys.exit(1)
    except OSError, e:
        print >> sys.stderr, 'subprocess call failed:', e
        sys.exit(1)


def setup_testfs():
    # Set up testfs with user_xattr, etc.
    subprocess.call(['umount', 'testfs'])
    ex('dd', 'if=/dev/zero', 'of=testfs.img', 'bs=1M', 'count=32')
    ex('mke2fs', '-F', '-j', '-m', '0', 'testfs.img')
    ex('rm', '-rf', 'testfs')
    os.mkdir('testfs')
    ex('mount', '-o', 'loop,acl,user_xattr', 'testfs.img', 'testfs')
    # Hide, so that tests can't create risks.
    ex('chown', 'root:root', 'testfs')
    os.chmod('testfs', 0700)


def cleanup_testfs():
    subprocess.call(['umount', 'testfs'])
    subprocess.call(['rm', '-f', 'testfs.img'])


@wvtest
def test_clean_up_archive_path():
    cleanup = metadata._clean_up_path_for_archive
    WVPASSEQ(cleanup('foo'), 'foo')
    WVPASSEQ(cleanup('/foo'), 'foo')
    WVPASSEQ(cleanup('///foo'), 'foo')
    WVPASSEQ(cleanup('/foo/bar'), 'foo/bar')
    WVPASSEQ(cleanup('foo/./bar'), 'foo/bar')
    WVPASSEQ(cleanup('/foo/./bar'), 'foo/bar')
    WVPASSEQ(cleanup('/foo/./bar/././baz'), 'foo/bar/baz')
    WVPASSEQ(cleanup('/foo/./bar///././baz'), 'foo/bar/baz')
    WVPASSEQ(cleanup('//./foo/./bar///././baz/.///'), 'foo/bar/baz/')
    WVPASSEQ(cleanup('./foo/./.bar'), 'foo/.bar')
    WVPASSEQ(cleanup('./foo/.'), 'foo')
    WVPASSEQ(cleanup('./foo/..'), '.')
    WVPASSEQ(cleanup('//./..//.../..//.'), '.')
    WVPASSEQ(cleanup('//./..//..././/.'), '...')
    WVPASSEQ(cleanup('/////.'), '.')
    WVPASSEQ(cleanup('/../'), '.')
    WVPASSEQ(cleanup(''), '.')


@wvtest
def test_risky_path():
    risky = metadata._risky_path
    WVPASS(risky('/foo'))
    WVPASS(risky('///foo'))
    WVPASS(risky('/../foo'))
    WVPASS(risky('../foo'))
    WVPASS(risky('foo/..'))
    WVPASS(risky('foo/../'))
    WVPASS(risky('foo/../bar'))
    WVFAIL(risky('foo'))
    WVFAIL(risky('foo/'))
    WVFAIL(risky('foo///'))
    WVFAIL(risky('./foo'))
    WVFAIL(risky('foo/.'))
    WVFAIL(risky('./foo/.'))
    WVFAIL(risky('foo/bar'))
    WVFAIL(risky('foo/./bar'))


@wvtest
def test_clean_up_extract_path():
    cleanup = metadata._clean_up_extract_path
    WVPASSEQ(cleanup('/foo'), 'foo')
    WVPASSEQ(cleanup('///foo'), 'foo')
    WVFAIL(cleanup('/../foo'))
    WVFAIL(cleanup('../foo'))
    WVFAIL(cleanup('foo/..'))
    WVFAIL(cleanup('foo/../'))
    WVFAIL(cleanup('foo/../bar'))
    WVPASSEQ(cleanup('foo'), 'foo')
    WVPASSEQ(cleanup('foo/'), 'foo/')
    WVPASSEQ(cleanup('foo///'), 'foo///')
    WVPASSEQ(cleanup('./foo'), './foo')
    WVPASSEQ(cleanup('foo/.'), 'foo/.')
    WVPASSEQ(cleanup('./foo/.'), './foo/.')
    WVPASSEQ(cleanup('foo/bar'), 'foo/bar')
    WVPASSEQ(cleanup('foo/./bar'), 'foo/./bar')
    WVPASSEQ(cleanup('/'), '.')
    WVPASSEQ(cleanup('./'), './')
    WVPASSEQ(cleanup('///foo/bar'), 'foo/bar')
    WVPASSEQ(cleanup('///foo/bar'), 'foo/bar')


@wvtest
def test_from_path_error():
    if os.geteuid() == 0 or detect_fakeroot():
        return
    tmpdir = tempfile.mkdtemp(prefix='bup-tmetadata-')
    try:
        path = tmpdir + '/foo'
        subprocess.call(['mkdir', path])
        m = metadata.from_path(path, archive_path=path, save_symlinks=True)
        WVPASSEQ(m.path, path)
        subprocess.call(['chmod', '000', path])
        metadata.from_path(path, archive_path=path, save_symlinks=True)
        errmsg = helpers.saved_errors[0] if helpers.saved_errors else ''
        WVPASS(errmsg.startswith('read Linux attr'))
        clear_errors()
    finally:
        subprocess.call(['rm', '-rf', tmpdir])


@wvtest
def test_apply_to_path_restricted_access():
    if os.geteuid() == 0 or detect_fakeroot():
        return
    tmpdir = tempfile.mkdtemp(prefix='bup-tmetadata-')
    try:
        path = tmpdir + '/foo'
        subprocess.call(['mkdir', path])
        clear_errors()
        m = metadata.from_path(path, archive_path=path, save_symlinks=True)
        WVPASSEQ(m.path, path)
        subprocess.call(['chmod', '000', tmpdir])
        m.apply_to_path(path)
        errmsg = str(helpers.saved_errors[0]) if helpers.saved_errors else ''
        WVPASS(errmsg.startswith('utime: '))
        clear_errors()
    finally:
        subprocess.call(['rm', '-rf', tmpdir])


@wvtest
def test_restore_restricted_user_group():
    if os.geteuid() == 0 or detect_fakeroot():
        return
    tmpdir = tempfile.mkdtemp(prefix='bup-tmetadata-')
    try:
        path = tmpdir + '/foo'
        subprocess.call(['mkdir', path])
        m = metadata.from_path(path, archive_path=path, save_symlinks=True)
        WVPASSEQ(m.path, path)
        WVPASSEQ(m.apply_to_path(path), None)
        orig_uid = m.uid
        m.uid = 0;
        m.apply_to_path(path, restore_numeric_ids=True)
        errmsg = str(helpers.saved_errors[0]) if helpers.saved_errors else ''
        WVPASS(errmsg.startswith('lchown: '))
        clear_errors()
        m.uid = orig_uid
        m.gid = 0;
        m.apply_to_path(path, restore_numeric_ids=True)
        errmsg = str(helpers.saved_errors[0]) if helpers.saved_errors else ''
        WVPASS(errmsg.startswith('lchown: ') or os.stat(path).st_gid == m.gid)
        clear_errors()
    finally:
        subprocess.call(['rm', '-rf', tmpdir])


@wvtest
def test_restore_nonexistent_user_group():
    tmpdir = tempfile.mkdtemp(prefix='bup-tmetadata-')
    try:
        path = tmpdir + '/foo'
        subprocess.call(['mkdir', path])
        m = metadata.from_path(path, archive_path=path, save_symlinks=True)
        WVPASSEQ(m.path, path)
        m.owner = max([x.pw_name for x in pwd.getpwall()], key=len) + 'x'
        m.group = max([x.gr_name for x in grp.getgrall()], key=len) + 'x'
        WVPASSEQ(m.apply_to_path(path, restore_numeric_ids=True), None)
        WVPASSEQ(os.stat(path).st_uid, m.uid)
        WVPASSEQ(os.stat(path).st_gid, m.gid)
        WVPASSEQ(m.apply_to_path(path, restore_numeric_ids=False), None)
        WVPASSEQ(os.stat(path).st_uid, os.geteuid())
        WVPASSEQ(os.stat(path).st_gid, os.getgid())
    finally:
        subprocess.call(['rm', '-rf', tmpdir])


@wvtest
def test_restore_over_existing_target():
    tmpdir = tempfile.mkdtemp(prefix='bup-tmetadata-')
    try:
        path = tmpdir + '/foo'
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
        open(path + '/bar', 'w').close()
        WVEXCEPT(Exception, file_m.create_path, path, create_symlinks=True)
        # Restore dir over non-empty dir.
        os.remove(path + '/bar')
        os.mkdir(path + '/bar')
        WVEXCEPT(Exception, dir_m.create_path, path, create_symlinks=True)
    finally:
        subprocess.call(['rm', '-rf', tmpdir])


@wvtest
def test_handling_of_incorrect_existing_linux_xattrs():
    if os.geteuid() != 0 or detect_fakeroot():
        return
    setup_testfs()
    subprocess.check_call('rm -rf testfs/*', shell=True)
    path = 'testfs/foo'
    open(path, 'w').close()
    xattr.set(path, 'foo', 'bar', namespace=xattr.NS_USER)
    m = metadata.from_path(path, archive_path=path, save_symlinks=True)
    xattr.set(path, 'baz', 'bax', namespace=xattr.NS_USER)
    m.apply_to_path(path, restore_numeric_ids=False)
    WVPASSEQ(xattr.list(path), ['user.foo'])
    WVPASSEQ(xattr.get(path, 'user.foo'), 'bar')
    xattr.set(path, 'foo', 'baz', namespace=xattr.NS_USER)
    m.apply_to_path(path, restore_numeric_ids=False)
    WVPASSEQ(xattr.list(path), ['user.foo'])
    WVPASSEQ(xattr.get(path, 'user.foo'), 'bar')
    xattr.remove(path, 'foo', namespace=xattr.NS_USER)
    m.apply_to_path(path, restore_numeric_ids=False)
    WVPASSEQ(xattr.list(path), ['user.foo'])
    WVPASSEQ(xattr.get(path, 'user.foo'), 'bar')
    os.chdir(top_dir)
    cleanup_testfs()
