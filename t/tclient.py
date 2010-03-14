import os, time, random
from bup import client, git, hashsplit
from wvtest import *

def randbytes(sz):
    s = ''
    for i in xrange(sz):
        s += chr(random.randrange(0,256))
    return s

@wvtest
def test_server_split_with_indexes():
    os.environ['BUP_MAIN_EXE'] = './bup'
    os.environ['BUP_DIR'] = bupdir = 'buptest_tclient.tmp'
    git.init_repo()
    git.check_repo_or_die()
    lw = git.PackWriter()
    c = client.Client(bupdir, create=True)
    rw = c.new_packwriter()

    s1 = randbytes(10000)
    s2 = randbytes(10000)
    
    lw.new_blob(s1)
    lw.close()

    rw.new_blob(s2)
    rw.breakpoint()
    rw.new_blob(s1)
    
