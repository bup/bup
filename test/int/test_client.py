
import os, time, random, subprocess, glob
import pytest

from bup import client, git, path
from bup.compat import bytes_from_uint, environ
from buptest import ex

def randbytes(sz):
    s = b''
    for i in range(sz):
        s += bytes_from_uint(random.randrange(0,256))
    return s


s1 = randbytes(10000)
s2 = randbytes(10000)
s3 = randbytes(10000)

IDX_PAT = b'/*.idx'


def test_server_split_with_indexes(tmpdir):
    environ[b'BUP_DIR'] = bupdir = tmpdir
    git.init_repo(bupdir)
    with git.PackWriter() as lw:
        lw.new_blob(s1)
    with client.Client(bupdir, create=True) as c, \
         c.new_packwriter() as rw:
        rw.new_blob(s2)
        rw.breakpoint()
        rw.new_blob(s1)


def test_multiple_suggestions(tmpdir):
    environ[b'BUP_DIR'] = bupdir = tmpdir
    git.init_repo(bupdir)

    with git.PackWriter() as lw:
        lw.new_blob(s1)
    with git.PackWriter() as lw:
        lw.new_blob(s2)
    assert len(glob.glob(git.repo(b'objects/pack'+IDX_PAT))) == 2

    with client.Client(bupdir, create=True) as c, \
         c.new_packwriter() as rw:

        assert len(glob.glob(c.cachedir+IDX_PAT)) == 0
        s1sha = rw.new_blob(s1)
        assert rw.exists(s1sha)
        s2sha = rw.new_blob(s2)

        # This is a little hacky, but ensures that we test the
        # code under test. First, flush to ensure that we've
        # actually sent all the command ('receive-objects-v2')
        # and their data to the server. This may be needed if
        # the output buffer size is bigger than the data (both
        # command and objects) we're writing. To see the need
        # for this, change the object sizes at the beginning
        # of this file to be very small (e.g. 10 instead of 10k)
        c.conn.outp.flush()

        # Then, check if we've already received the idx files.
        # This may happen if we're preempted just after writing
        # the data, then the server runs and suggests, and only
        # then we continue in PackWriter_Remote::_raw_write()
        # and check the has_input(), in that case we'll receive
        # the idx still in the rw.new_blob() calls above.
        #
        # In most cases though, that doesn't happen, and we'll
        # get past the has_input() check before the server has
        # a chance to respond - it has to actually hash the new
        # object here, so it takes some time. So also break out
        # of the loop if the server has sent something on the
        # connection.
        #
        # Finally, abort this after a little while (about one
        # second) just in case something's actually broken.
        n = 0
        while (len(glob.glob(c.cachedir+IDX_PAT)) < 2 and
               not c.conn.has_input() and n < 10):
            time.sleep(0.1)
            n += 1
        assert len(glob.glob(c.cachedir+IDX_PAT)) == 2 or c.conn.has_input()
        rw.new_blob(s2)
        assert rw.objcache.exists(s1sha)
        assert rw.objcache.exists(s2sha)
        rw.new_blob(s3)
        assert len(glob.glob(c.cachedir+IDX_PAT)) == 2
    assert len(glob.glob(c.cachedir+IDX_PAT)) == 3


def test_dumb_client_server(tmpdir):
    environ[b'BUP_DIR'] = bupdir = tmpdir
    git.init_repo(bupdir)
    open(git.repo(b'bup-dumb-server'), 'w').close()

    with git.PackWriter() as lw:
        lw.new_blob(s1)

    with client.Client(bupdir, create=True) as c, \
         c.new_packwriter() as rw:
        assert len(glob.glob(c.cachedir+IDX_PAT)) == 1
        rw.new_blob(s1)
        assert len(glob.glob(c.cachedir+IDX_PAT)) == 1
        rw.new_blob(s2)
    assert len(glob.glob(c.cachedir+IDX_PAT)) == 2


def test_midx_refreshing(tmpdir):
    environ[b'BUP_DIR'] = bupdir = tmpdir
    git.init_repo(bupdir)
    with client.Client(bupdir, create=True) as c, \
         c.new_packwriter() as rw:
        rw.new_blob(s1)
        p1base = rw.breakpoint()
        p1name = os.path.join(c.cachedir, p1base)
        s1sha = rw.new_blob(s1)  # should not be written; it's already in p1
        s2sha = rw.new_blob(s2)
        p2base = rw.close()
    p2name = os.path.join(c.cachedir, p2base)

    with git.PackIdxList(bupdir + b'/objects/pack') as pi:
        assert len(pi.packs) == 2
        pi.refresh()
        assert len(pi.packs) == 2
        assert sorted([os.path.basename(i.name) for i in pi.packs]) \
            == sorted([p1base, p2base])

        with git.open_idx(p1name) as p1, \
             git.open_idx(p2name) as p2:
            assert p1.exists(s1sha)
            assert not p2.exists(s1sha)
            assert p2.exists(s2sha)

        subprocess.call([path.exe(), b'midx', b'-f'])
        pi.refresh()
        assert len(pi.packs) == 1
        pi.refresh(skip_midx=True)
        assert len(pi.packs) == 2
        pi.refresh(skip_midx=False)
        assert len(pi.packs) == 1


def test_remote_parsing():
    tests = (
        (b':/bup', (b'file', None, None, b'/bup')),
        (b'file:///bup', (b'file', None, None, b'/bup')),
        (b'192.168.1.1:/bup', (b'ssh', b'192.168.1.1', None, b'/bup')),
        (b'ssh://192.168.1.1:2222/bup', (b'ssh', b'192.168.1.1', b'2222', b'/bup')),
        (b'ssh://[ff:fe::1]:2222/bup', (b'ssh', b'ff:fe::1', b'2222', b'/bup')),
        (b'bup://foo.com:1950', (b'bup', b'foo.com', b'1950', None)),
        (b'bup://foo.com:1950/bup', (b'bup', b'foo.com', b'1950', b'/bup')),
        (b'bup://[ff:fe::1]/bup', (b'bup', b'ff:fe::1', None, b'/bup')),
        (b'bup://[ff:fe::1]/bup', (b'bup', b'ff:fe::1', None, b'/bup')),
        (b'bup-rev://', (b'bup-rev', None, None, b'')),
        (b'bup-rev://host/dir', (b'bup-rev', b'host', None, b'/dir')),
    )
    for remote, values in tests:
        assert client.parse_remote(remote) == values

    with pytest.raises(client.ClientError):
        client.parse_remote(b'http://asdf.com/bup')

def test_config(tmpdir):
    environ[b'BUP_DIR'] = bupdir = tmpdir
    environ[b'GIT_DIR'] = bupdir = tmpdir
    git.init_repo(bupdir)
    with client.Client(bupdir, create=True) as c:
        assert c.config_get(b'bup.split-trees') is None
        assert c.config_get(b'bup.split-trees', opttype='int') is None
        ex((b'git', b'config', b'bup.split-trees', b'0'))
        assert c.config_get(b'bup.split-trees') == b'0'
        assert c.config_get(b'bup.split-trees', opttype='int') == 0
        ex((b'git', b'config', b'bup.split-trees', b'1'))
        assert c.config_get(b'bup.split-trees', opttype='bool') == True
        with pytest.raises(PermissionError) as exinfo:
            c.config_get(b'bup.not-an-allowed-key')
        assert 'does not allow remote access' in str(exinfo.value)
