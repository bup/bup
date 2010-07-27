from bup import hashsplit, _hashsplit
from wvtest import *

@wvtest
def test_rolling_sums():
    WVPASS(_hashsplit.selftest())
