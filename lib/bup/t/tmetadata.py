import grp
import pwd
import stat
import subprocess
import tempfile
from bup import metadata
from bup.helpers import detect_fakeroot, saved_errors
from wvtest import *


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
    if os.geteuid == 0 or detect_fakeroot():
        return
    tmpdir = tempfile.mkdtemp(prefix='bup-tmetadata-')
    try:
        path = tmpdir + '/foo'
        subprocess.call(['mkdir', path])
        m = metadata.from_path(path, archive_path=path, save_symlinks=True)
        WVPASSEQ(m.path, path)
        subprocess.call(['chmod', '000', path])
        metadata.from_path(path, archive_path=path, save_symlinks=True)
        WVPASS(saved_errors
               and saved_errors[0].startswith('bup: unable to read Linux attr'))
    finally:
        subprocess.call(['rm', '-rf', tmpdir])


@wvtest
def test_apply_to_path_error():
    if os.geteuid == 0 or detect_fakeroot():
        return
    tmpdir = tempfile.mkdtemp(prefix='bup-tmetadata-')
    try:
        path = tmpdir + '/foo'
        subprocess.call(['mkdir', path])
        m = metadata.from_path(path, archive_path=path, save_symlinks=True)
        WVPASSEQ(m.path, path)
        subprocess.call(['chmod', '000', tmpdir])
        WVEXCEPT(metadata.MetadataApplyError,
                 m.apply_to_path, path)
        subprocess.call(['chmod', '700', tmpdir])
    finally:
        subprocess.call(['rm', '-rf', tmpdir])


@wvtest
def test_restore_restricted_user_group():
    if os.geteuid == 0 or detect_fakeroot():
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
        WVEXCEPT(metadata.MetadataApplyError,
                 m.apply_to_path, path, restore_numeric_ids=True)
        m.uid = orig_uid
        m.gid = 0;
        WVEXCEPT(metadata.MetadataApplyError,
                 m.apply_to_path, path, restore_numeric_ids=True)
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
        WVPASSEQ(os.stat(path).st_uid, os.getgid())
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
