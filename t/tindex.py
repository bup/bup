import os
import index
from wvtest import *

@wvtest
def testbasic():
    cd = os.path.realpath('')
    WVPASS(cd)
    sd = os.path.realpath('t/sampledata')
    WVPASSEQ(index.realpath('t/sampledata'), cd + '/t/sampledata')
    WVPASSEQ(os.path.realpath('t/sampledata/x'), sd + '/x')
    WVPASSEQ(os.path.realpath('t/sampledata/etc'), os.path.realpath('/etc'))
    WVPASSEQ(index.realpath('t/sampledata/etc'), sd + '/etc')
