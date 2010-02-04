import os
import index
from wvtest import *
from helpers import *

@wvtest
def testbasic():
    cd = os.path.realpath('')
    WVPASS(cd)
    sd = os.path.realpath('t/sampledata')
    WVPASSEQ(index.realpath('t/sampledata'), cd + '/t/sampledata')
    WVPASSEQ(os.path.realpath('t/sampledata/x'), sd + '/x')
    WVPASSEQ(os.path.realpath('t/sampledata/etc'), os.path.realpath('/etc'))
    WVPASSEQ(index.realpath('t/sampledata/etc'), sd + '/etc')


@wvtest
def testwriter():
    unlink('index.tmp')
    ds = os.stat('.')
    fs = os.stat('t/tindex.py')
    w = index.Writer('index.tmp')
    w.add('/var/tmp/sporky', fs)
    w.add('/etc/passwd', fs)
    w.add('/etc/', ds)
    w.add('/', ds)
    w.close()
