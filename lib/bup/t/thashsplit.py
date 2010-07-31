from bup import hashsplit, _faster
from wvtest import *

@wvtest
def test_rolling_sums():
    WVPASS(_faster.selftest())
