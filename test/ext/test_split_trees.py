
from os import chdir, environb as environ, mkdir
from os.path import join as pj
import pytest

from buptest import ex, exo
import bup.path


bup = bup.path.exe()

@pytest.fixture
def large_tree(tmpdir):
    # pytest fixtures are cached, so there will be only one large tree
    for i in range(10000):
        d = b'%s/some-random-path-name-to-make-the-tree-bigger-%d' % (tmpdir, i)
        mkdir(d)
        with open(pj(d, b'data'), 'w') as f:
            print('data', file=f)
    return tmpdir

def test_large_tree(tmpdir, large_tree):
    environ[b'GIT_DIR'] = tmpdir + b'/repo'
    environ[b'BUP_DIR'] = tmpdir + b'/repo'
    chdir(tmpdir)
    ex((bup, b'init'))
    ex((b'git', b'config', b'bup.split.trees', b'true'))
    ex((bup, b'index', large_tree))
    ex((bup, b'save', b'-n', b'gc-test', b'--strip', large_tree))

    bupd = None
    for p in exo((b'git', b'ls-tree', b'gc-test')).out.splitlines():
        if p.endswith(b'.bupd'):
            bupd = p
            break
    assert bupd, 'split-tree .bupd not found'

    ex((bup, b'gc', b'--unsafe', b'-v'))
