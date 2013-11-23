from bup import hashsplit, _helpers
from wvtest import *
from cStringIO import StringIO

@wvtest
def test_rolling_sums():
    WVPASS(_helpers.selftest())

@wvtest
def test_fanout_behaviour():

    # Drop in replacement for bupsplit, but splitting if the int value of a
    # byte >= BUP_BLOBBITS
    basebits = _helpers.blobbits()
    def splitbuf(buf):
        ofs = 0
        for c in buf:
            ofs += 1
            if ord(c) >= basebits:
                return ofs, ord(c)
        return 0, 0

    old_splitbuf = _helpers.splitbuf
    _helpers.splitbuf = splitbuf
    old_BLOB_MAX = hashsplit.BLOB_MAX
    hashsplit.BLOB_MAX = 4
    old_BLOB_READ_SIZE = hashsplit.BLOB_READ_SIZE
    hashsplit.BLOB_READ_SIZE = 10
    old_fanout = hashsplit.fanout
    hashsplit.fanout = 2

    levels = lambda f: [(len(b), l) for b, l in
        hashsplit.hashsplit_iter([f], True, None)]
    # Return a string of n null bytes
    z = lambda n: '\x00' * n
    # Return a byte which will be split with a level of n
    sb = lambda n: chr(basebits + n)

    split_never = StringIO(z(16))
    split_first = StringIO(z(1) + sb(3) + z(14))
    split_end   = StringIO(z(13) + sb(1) + z(2))
    split_many  = StringIO(sb(1) + z(3) + sb(2) + z(4) +
                            sb(0) + z(4) + sb(5) + z(1))
    WVPASSEQ(levels(split_never), [(4, 0), (4, 0), (4, 0), (4, 0)])
    WVPASSEQ(levels(split_first), [(2, 3), (4, 0), (4, 0), (4, 0), (2, 0)])
    WVPASSEQ(levels(split_end), [(4, 0), (4, 0), (4, 0), (2, 1), (2, 0)])
    WVPASSEQ(levels(split_many),
        [(1, 1), (4, 2), (4, 0), (1, 0), (4, 0), (1, 5), (1, 0)])

    _helpers.splitbuf = old_splitbuf
    hashsplit.BLOB_MAX = old_BLOB_MAX
    hashsplit.BLOB_READ_SIZE = old_BLOB_READ_SIZE
    hashsplit.fanout = old_fanout
