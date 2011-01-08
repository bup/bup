import sys, os, time, random, subprocess
from bup import client, git
from wvtest import *

def randbytes(sz):
    s = ''
    for i in xrange(sz):
        s += chr(random.randrange(0,256))
    return s

s1 = randbytes(10000)
s2 = randbytes(10000)
s3 = randbytes(10000)
    
@wvtest
def test_server_split_with_indexes():
    os.environ['BUP_MAIN_EXE'] = '../../../bup'
    os.environ['BUP_DIR'] = bupdir = 'buptest_tclient.tmp'
    subprocess.call(['rm', '-rf', bupdir])
    git.init_repo(bupdir)
    lw = git.PackWriter()
    c = client.Client(bupdir, create=True)
    rw = c.new_packwriter()

    lw.new_blob(s1)
    lw.close()

    rw.new_blob(s2)
    rw.breakpoint()
    rw.new_blob(s1)
    

@wvtest
def test_multiple_suggestions():
    os.environ['BUP_MAIN_EXE'] = '../../../bup'
    os.environ['BUP_DIR'] = bupdir = 'buptest_tclient.tmp'
    subprocess.call(['rm', '-rf', bupdir])
    git.init_repo(bupdir)

    lw = git.PackWriter()
    lw.new_blob(s1)
    lw.close()
    lw = git.PackWriter()
    lw.new_blob(s2)
    lw.close()
    WVPASSEQ(len(os.listdir(git.repo('objects/pack'))), 4)

    c = client.Client(bupdir, create=True)
    WVPASSEQ(len(os.listdir(c.cachedir)), 0)
    rw = c.new_packwriter()
    rw.new_blob(s1)
    rw.new_blob(s2)
    rw.new_blob(s3)
    WVPASSEQ(len(os.listdir(c.cachedir)), 2)
    rw.close()
    WVPASSEQ(len(os.listdir(c.cachedir)), 3)


@wvtest
def test_dumb_client_server():
    os.environ['BUP_MAIN_EXE'] = '../../../bup'
    os.environ['BUP_DIR'] = bupdir = 'buptest_tclient.tmp'
    subprocess.call(['rm', '-rf', bupdir])
    git.init_repo(bupdir)
    os.mknod(git.repo('bup-dumb-server'))

    lw = git.PackWriter()
    lw.new_blob(s1)
    lw.close()

    c = client.Client(bupdir, create=True)
    rw = c.new_packwriter()
    WVPASSEQ(len(os.listdir(c.cachedir)), 1)
    rw.new_blob(s1)
    WVPASSEQ(len(os.listdir(c.cachedir)), 1)
    rw.new_blob(s2)
    rw.close()
    WVPASSEQ(len(os.listdir(c.cachedir)), 2)


@wvtest
def test_midx_refreshing():
    os.environ['BUP_MAIN_EXE'] = bupmain = '../../../bup'
    os.environ['BUP_DIR'] = bupdir = 'buptest_tmidx.tmp'
    subprocess.call(['rm', '-rf', bupdir])
    git.init_repo(bupdir)
    lw = git.PackWriter()
    lw.new_blob(s1)
    lw.breakpoint()
    lw.new_blob(s2)
    del lw
    pi = git.PackIdxList(bupdir + '/objects/pack')
    WVPASSEQ(len(pi.packs), 2)
    pi.refresh()
    WVPASSEQ(len(pi.packs), 2)
    subprocess.call([bupmain, 'midx', '-f'])
    pi.refresh()
    WVPASSEQ(len(pi.packs), 1)
    pi.refresh(skip_midx=True)
    WVPASSEQ(len(pi.packs), 2)
    pi.refresh(skip_midx=False)
    WVPASSEQ(len(pi.packs), 1)

@wvtest
def test_remote_parsing():
    tests = (
        (':/bup', ('file', None, None, '/bup')),
        ('file:///bup', ('file', None, None, '/bup')),
        ('192.168.1.1:/bup', ('ssh', '192.168.1.1', None, '/bup')),
        ('ssh://192.168.1.1:2222/bup', ('ssh', '192.168.1.1', '2222', '/bup')),
        ('ssh://[ff:fe::1]:2222/bup', ('ssh', 'ff:fe::1', '2222', '/bup')),
        ('bup://foo.com:1950', ('bup', 'foo.com', '1950', None)),
        ('bup://foo.com:1950/bup', ('bup', 'foo.com', '1950', '/bup')),
        ('bup://[ff:fe::1]/bup', ('bup', 'ff:fe::1', None, '/bup')),
    )
    for remote, values in tests:
        WVPASSEQ(client.parse_remote(remote), values)
    try:
        client.parse_remote('http://asdf.com/bup')
        WVFAIL()
    except AssertionError:
        WVPASS()
