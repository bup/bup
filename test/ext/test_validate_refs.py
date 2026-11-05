
from io import BytesIO
from os import chdir, environb as environ, mkdir
from subprocess import PIPE
from sys import stderr
import re

from buptest import exc as ex, exo
import bup.path

from bup import metadata


# Additional tests are in test-validate-refs and more --links tests
# are handled in test-validate-ref-links.

bup = bup.path.exe()

def test_detect_missing_common_rec(tmpdir):
    environ[b'GIT_DIR'] = tmpdir + b'/repo'
    environ[b'BUP_DIR'] = tmpdir + b'/repo'

    # Save a root tree with three bupm entries
    chdir(tmpdir)
    ex(bup, b'init')
    mkdir(b'src')
    with open(b'src/1', 'w', encoding='utf-8') as f: print(1, file=f)
    with open(b'src/2', 'w', encoding='utf-8') as f: print(2, file=f)
    ex(bup, b'index', b'src')
    res = exo(bup, b'save', b'--strip', b'-n', b'src', b'src')

    # Create and store a bupm with no common_rec in the src/1 entry
    res = exo(bup, b'cat-file', b'--bupm', b'src/latest/')
    bupm = metadata._ArchiveIterator(BytesIO(res.out))
    with open(b'broken-bupm', 'wb') as broken:
        i = 0
        for meta in bupm:
            i += 1
            if i != 2:
                meta.write(broken, include_path=False)
                continue
            meta.thaw()
            meta.mode = None # cf. _encode_common
            meta.write(broken, include_path=False, require_common=False)
        assert i == 3
    res = exo(b'git', b'hash-object', b'-w', b'broken-bupm')
    broken_oidx = res.out.strip()
    assert len(broken_oidx) == 40

    # Manually create a new commit including the broken bupm
    res = exo(b'git', b'ls-tree', b'src')
    tree = res.out.splitlines()
    new_tree = []
    bupms = 0
    for ent in tree:
        if not ent.endswith(b'.bupm'):
            new_tree.append(ent)
            continue
        bupms += 1
        new_ent = re.sub(b'[0-9a-f]{40}', broken_oidx, ent)
        assert broken_oidx in new_ent
        new_tree.append(new_ent)
    assert bupms == 1
    res = exo(b'git', b'mktree', input=b'\n'.join(new_tree))
    new_tree_oidx = res.out.strip()
    assert len(new_tree_oidx) == 40
    res = exo(b'git', b'commit-tree', new_tree_oidx, b'-p', b'src',
              b'-m', b'missing common rec')
    new_commit_oidx = res.out.strip()
    assert len(new_commit_oidx) == 40
    ex(b'git', b'branch', b'-f', b'src', new_commit_oidx)

    # Check it
    res = ex(bup, b'validate-refs', b'--bupm', check=False, stderr=PIPE)
    stderr.flush()
    stderr.buffer.write(res.err)
    assert res.rc == 2
    msg = b':.bupm via refs/heads/src %s:.bupm omits common records (please report)' \
        % new_tree_oidx
    found = False
    lines = res.err.splitlines()
    for line in lines:
        if line.endswith(msg):
            found = True
            break
    assert found, lines
