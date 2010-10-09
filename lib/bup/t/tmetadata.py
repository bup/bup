import tempfile
import subprocess
from bup import metadata
from bup.helpers import detect_fakeroot
from wvtest import *


@wvtest
def test__normalize_ts():
    normalize = metadata._normalize_ts
    bns = 10**9
    for ts in ((0, 0), (-1, 0), (0, bns - 1), (-1, bns - 1)):
        WVPASSEQ(normalize(ts), ts)
    WVPASSEQ(normalize((0, -1)), (-1, bns - 1))
    WVPASSEQ(normalize((-1, -1)), (-2, bns - 1))
    WVPASSEQ(normalize((0, bns)), (1, 0))
    WVPASSEQ(normalize((0, bns + 1)), (1, 1))
    WVPASSEQ(normalize((0, -bns)), (-1, 0))
    WVPASSEQ(normalize((0, -(bns + 1))), (-2, bns - 1))
    WVPASSEQ(normalize((0, 3 * bns)), (3, 0))
    WVPASSEQ(normalize((0, -3 * bns)), (-3, 0))


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
        WVEXCEPT(metadata.MetadataAcquisitionError,
                 metadata.from_path,
                 path,
                 archive_path=path,
                 save_symlinks=True)
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
        WVEXCEPT(metadata.MetadataApplicationError,
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
        WVEXCEPT(metadata.MetadataApplicationError,
                 m.apply_to_path, path, restore_numeric_ids=True)
        m.uid = orig_uid
        m.gid = 0;
        WVEXCEPT(metadata.MetadataApplicationError,
                 m.apply_to_path, path, restore_numeric_ids=True)
    finally:
        subprocess.call(['rm', '-rf', tmpdir])
