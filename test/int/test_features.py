
from platform import python_version

from buptest import exc, exo

from bup import features, version
import bup.path


bup_path = bup.path.exe()


def test_default_output():
    provides = features.get()['provides']
    def yn(p): return b'yes' if p in provides else b'no'

    res = exo(bup_path, 'features')
    l = res.out.splitlines()
    assert l[0] == b'bup ' + version.version
    assert l[1] == b'Source %s %s' % (version.commit, version.date)
    assert l[2][4:] == b'Python: ' + python_version().encode('ascii')
    assert l[3][4:] == b'Command line editing (e.g. bup ftp): ' + yn('readline')
    assert l[4][4:] == b'Saving and restoring POSIX ACLs: ' + yn('posix1e-acls')
    assert l[5][4:] == b'Saving and restoring extended attributes (xattrs): '\
        + yn('linux-xattrs')


def test_provides():
    provides = features.get()['provides']
    def ex_rc(p): return 0 if p in provides else 1

    for feature in ('nope', 'readline', 'posix1e-acls', 'linux-xattrs'):
        res = exc(bup_path, 'features', '--provides', feature, check=False)
        assert res.rc == ex_rc(feature)
