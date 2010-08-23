from bup import hashsplit, _helpers
from wvtest import *

@wvtest
def test_rolling_sums():
    WVPASS(_helpers.selftest())
