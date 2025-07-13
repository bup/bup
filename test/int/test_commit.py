
from os import environb as environ
from subprocess import check_call
import sys

from wvpytest import *

from bup import git
from bup.commit import _git_date_str, parse_commit
from bup.helpers import readpipe


def exc(*cmd):
    print(repr(cmd), file=sys.stderr)
    check_call(cmd)


def test_commit_parsing(tmpdir):
    def restore_env_var(name, val):
        if val is None:
            del environ[name]
        else:
            environ[name] = val

    def showval(commit, val):
        return readpipe([b'git', b'show', b'-s',
                         b'--pretty=format:%s' % val, commit]).strip()

    orig_cwd = os.getcwd()
    workdir = tmpdir + b'/work'
    repodir = workdir + b'/.git'
    orig_author_name = environ.get(b'GIT_AUTHOR_NAME')
    orig_author_email = environ.get(b'GIT_AUTHOR_EMAIL')
    orig_committer_name = environ.get(b'GIT_COMMITTER_NAME')
    orig_committer_email = environ.get(b'GIT_COMMITTER_EMAIL')
    environ[b'GIT_AUTHOR_NAME'] = b'bup test'
    environ[b'GIT_COMMITTER_NAME'] = environ[b'GIT_AUTHOR_NAME']
    environ[b'GIT_AUTHOR_EMAIL'] = b'bup@a425bc70a02811e49bdf73ee56450e6f'
    environ[b'GIT_COMMITTER_EMAIL'] = environ[b'GIT_AUTHOR_EMAIL']
    try:
        environ[b'GIT_DIR'] = environ[b'BUP_DIR'] = repodir
        readpipe([b'git', b'init', workdir])
        exc(b'git', b'symbolic-ref', b'HEAD', b'refs/heads/main')
        git.check_repo_or_die(repodir)
        os.chdir(workdir)
        with open('foo', 'w') as f:
            print('bar', file=f)
        readpipe([b'git', b'add', b'.'])
        readpipe([b'git', b'commit', b'-am', b'Do something',
                  b'--author', b'Someone <someone@somewhere>',
                  b'--date', b'Sat Oct 3 19:48:49 2009 -0400'])
        commit = readpipe([b'git', b'show-ref', b'-s', b'main']).strip()
        parents = showval(commit, b'%P')
        tree = showval(commit, b'%T')
        cname = showval(commit, b'%cn')
        cmail = showval(commit, b'%ce')
        cdate = showval(commit, b'%ct')
        coffs = showval(commit, b'%ci')
        coffs = coffs[-5:]
        coff = (int(coffs[-4:-2]) * 60 * 60) + (int(coffs[-2:]) * 60)
        if coffs[-5] == b'-'[0]:
            coff = - coff
        commit_items = git.get_commit_items(commit, git.cp())
        WVPASSEQ(commit_items.parents, [])
        WVPASSEQ(commit_items.tree, tree)
        WVPASSEQ(commit_items.author_name, b'Someone')
        WVPASSEQ(commit_items.author_mail, b'someone@somewhere')
        WVPASSEQ(commit_items.author_sec, 1254613729)
        WVPASSEQ(commit_items.author_offset, -(4 * 60 * 60))
        WVPASSEQ(commit_items.committer_name, cname)
        WVPASSEQ(commit_items.committer_mail, cmail)
        WVPASSEQ(commit_items.committer_sec, int(cdate))
        WVPASSEQ(commit_items.committer_offset, coff)
        WVPASSEQ(commit_items.message, b'Do something\n')
        with open(b'bar', 'wb') as f:
            f.write(b'baz\n')
        readpipe([b'git', b'add', '.'])
        readpipe([b'git', b'commit', b'-am', b'Do something else'])
        child = readpipe([b'git', b'show-ref', b'-s', b'main']).strip()
        parents = showval(child, b'%P')
        commit_items = git.get_commit_items(child, git.cp())
        WVPASSEQ(commit_items.parents, [commit])
    finally:
        os.chdir(orig_cwd)
        restore_env_var(b'GIT_AUTHOR_NAME', orig_author_name)
        restore_env_var(b'GIT_AUTHOR_EMAIL', orig_author_email)
        restore_env_var(b'GIT_COMMITTER_NAME', orig_committer_name)
        restore_env_var(b'GIT_COMMITTER_EMAIL', orig_committer_email)


gpgsig_example_1 = b'''tree 3fab08ade2fbbda60bef180bb8e0cc5724d6bd4d
parent 36db87b46a95ca5079f43dfe9b72220acab7c731
author Rob Browning <rlb@defaultvalue.org> 1633397238 -0500
committer Rob Browning <rlb@defaultvalue.org> 1633397238 -0500
gpgsig -----BEGIN PGP SIGNATURE-----
 
 ...
 -----END PGP SIGNATURE-----

Sample signed commit.
'''

gpgsig_example_2 = b'''tree 3fab08ade2fbbda60bef180bb8e0cc5724d6bd4d
parent 36db87b46a95ca5079f43dfe9b72220acab7c731
author Rob Browning <rlb@defaultvalue.org> 1633397238 -0500
committer Rob Browning <rlb@defaultvalue.org> 1633397238 -0500
gpgsig -----BEGIN PGP SIGNATURE-----
 
 ...
 -----END PGP SIGNATURE-----
 

Sample signed commit.
'''

def test_commit_gpgsig_parsing():
    c = parse_commit(gpgsig_example_1)
    assert c.gpgsig
    assert c.gpgsig.startswith(b'-----BEGIN PGP SIGNATURE-----\n')
    assert c.gpgsig.endswith(b'\n-----END PGP SIGNATURE-----\n')
    c = git.parse_commit(gpgsig_example_2)
    assert c.gpgsig
    assert c.gpgsig.startswith(b'-----BEGIN PGP SIGNATURE-----')
    assert c.gpgsig.endswith(b'\n-----END PGP SIGNATURE-----\n\n')


def test_git_date_str():
    WVPASSEQ(b'0 +0000', _git_date_str(0, 0))
    WVPASSEQ(b'0 -0130', _git_date_str(0, -90 * 60))
    WVPASSEQ(b'0 +0130', _git_date_str(0, 90 * 60))
