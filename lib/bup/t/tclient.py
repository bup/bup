import sys, os, time, random, subprocess
from bup import client, git, hashsplit
from wvtest import *

def randbytes(sz):
    s = ''
    for i in xrange(sz):
        s += chr(random.randrange(0,256))
    return s

s1 = randbytes(10000)
s2 = randbytes(10000)
    
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
