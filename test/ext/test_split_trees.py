
from os import chdir, environb as environ
from os.path import join as joinp
import pytest

from buptest import ex, exo
import bup.path


bup = bup.path.exe()

def test_large_tree(tmpdir):
    environ[b'GIT_DIR'] = tmpdir + b'/repo'
    environ[b'BUP_DIR'] = tmpdir + b'/repo'

    ex((b'dev/make-splittable-tree', joinp(tmpdir, b'src')))

    chdir(tmpdir)
    ex((bup, b'init'))
    ex((b'git', b'config', b'bup.split.trees', b'true'))
    ex((bup, b'index', b'src'))
    ex((bup, b'save', b'-n', b'gc-test', b'--strip', b'src'))

    bupd = None
    for p in exo((b'git', b'ls-tree', b'gc-test')).out.splitlines():
        if p.endswith(b'.bupd'):
            bupd = p
            break
    assert bupd, 'split-tree .bupd not found'

    ex((bup, b'gc', b'--unsafe', b'-v'))
