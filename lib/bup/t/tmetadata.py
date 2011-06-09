import glob, grp, pwd, stat, tempfile, subprocess
import bup.helpers as helpers
from bup import metadata
from bup.helpers import clear_errors, detect_fakeroot, is_superuser
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
    os.chown('testfs', 0, 0)
    os.chmod('testfs', 0700)


def cleanup_testfs():
    subprocess.call(['umount', 'testfs'])
    helpers.unlink('testfs.img')


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


def _first_err():
    if helpers.saved_errors:
        return str(helpers.saved_errors[0])
    return ''


@wvtest
def test_from_path_error():
    if is_superuser() or detect_fakeroot():
        return
    tmpdir = tempfile.mkdtemp(prefix='bup-tmetadata-')
    try:
        path = tmpdir + '/foo'
        os.mkdir(path)
        m = metadata.from_path(path, archive_path=path, save_symlinks=True)
        WVPASSEQ(m.path, path)
        os.chmod(path, 000)
        metadata.from_path(path, archive_path=path, save_symlinks=True)
        if metadata.get_linux_file_attr:
            WVPASS(len(helpers.saved_errors) == 1)
            errmsg = _first_err()
            WVPASS(errmsg.startswith('read Linux attr'))
            clear_errors()
    finally:
        subprocess.call(['rm', '-rf', tmpdir])


@wvtest
def test_apply_to_path_restricted_access():
    if is_superuser() or detect_fakeroot():
        return
    tmpdir = tempfile.mkdtemp(prefix='bup-tmetadata-')
    try:
        path = tmpdir + '/foo'
        os.mkdir(path)
        clear_errors()
        m = metadata.from_path(path, archive_path=path, save_symlinks=True)
        WVPASSEQ(m.path, path)
        os.chmod(tmpdir, 000)
        m.apply_to_path(path)
        WVPASS(len(helpers.saved_errors) == 1)
        errmsg = _first_err()
        WVPASS(errmsg.startswith('utime: '))
        clear_errors()
    finally:
        subprocess.call(['rm', '-rf', tmpdir])


@wvtest
def test_restore_restricted_user_group():
    if is_superuser() or detect_fakeroot():
        return
    tmpdir = tempfile.mkdtemp(prefix='bup-tmetadata-')
    try:
        path = tmpdir + '/foo'
        os.mkdir(path)
        m = metadata.from_path(path, archive_path=path, save_symlinks=True)
        WVPASSEQ(m.path, path)
        WVPASSEQ(m.apply_to_path(path), None)
        orig_uid = m.uid
        m.uid = 0;
        m.apply_to_path(path, restore_numeric_ids=True)
        WVPASS(len(helpers.saved_errors) == 1)
        errmsg = _first_err()
        WVPASS(errmsg.startswith('lchown: '))
        clear_errors()
        m.uid = orig_uid
        m.gid = 0;
        m.apply_to_path(path, restore_numeric_ids=True)
        WVPASS(len(helpers.saved_errors) == 1)
        errmsg = _first_err()
        WVPASS(errmsg.startswith('lchown: ') or os.stat(path).st_gid == m.gid)
        clear_errors()
    finally:
        subprocess.call(['rm', '-rf', tmpdir])


@wvtest
def test_restore_nonexistent_user_group():
    tmpdir = tempfile.mkdtemp(prefix='bup-tmetadata-')
    try:
        path = tmpdir + '/foo'
        os.mkdir(path)
        m = metadata.from_path(path, archive_path=path, save_symlinks=True)
        WVPASSEQ(m.path, path)
        junk,m.owner = max([(len(x.pw_name), x.pw_name + 'x')
        		    for x in pwd.getpwall()])
        junk,m.group = max([(len(x.gr_name), x.gr_name + 'x')
                            for x in grp.getgrall()])
        WVPASSEQ(m.apply_to_path(path, restore_numeric_ids=True), None)
        WVPASSEQ(os.stat(path).st_uid, m.uid)
        WVPASSEQ(os.stat(path).st_gid, m.gid)
        WVPASSEQ(m.apply_to_path(path, restore_numeric_ids=False), None)
        WVPASSEQ(os.stat(path).st_uid, m.uid)
        WVPASSEQ(os.stat(path).st_gid, m.gid)
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


from bup.metadata import posix1e
if not posix1e:
    @wvtest
    def POSIX1E_ACL_SUPPORT_IS_MISSING():
        pass


from bup.metadata import xattr
if not xattr:
    @wvtest
    def LINUX_XATTR_SUPPORT_IS_MISSING():
        pass
else:
    @wvtest
    def test_handling_of_incorrect_existing_linux_xattrs():
        if not is_superuser():
            return
        setup_testfs()
        for f in glob.glob('testfs/*'):
            ex('rm', '-rf', f)
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
