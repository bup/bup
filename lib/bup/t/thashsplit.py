from bup import hashsplit, _helpers
from wvtest import *
from cStringIO import StringIO

def bytestr(x):
    return ''.join(map(chr, x))

@wvtest
def test_nonresident_page_regions():
    rpr = hashsplit._nonresident_page_regions
    x = bytestr([])
    WVPASSEQ(list(rpr(x)), [])
    x = bytestr([1])
    WVPASSEQ(list(rpr(x)), [])
    x = bytestr([0])
    WVPASSEQ(list(rpr(x)), [(0, 1)])
    x = bytestr([1, 0])
    WVPASSEQ(list(rpr(x)), [(1, 1)])
    x = bytestr([0, 0])
    WVPASSEQ(list(rpr(x)), [(0, 2)])
    x = bytestr([1, 0, 1])
    WVPASSEQ(list(rpr(x)), [(1, 1)])
    x = bytestr([1, 0, 0])
    WVPASSEQ(list(rpr(x)), [(1, 2)])
    x = bytestr([0, 1, 0])
    WVPASSEQ(list(rpr(x)), [(0, 1), (2, 1)])
    x = bytestr([0, 0, 1, 1, 1, 0, 0, 0, 1, 0, 0])
    WVPASSEQ(list(rpr(x)), [(0, 2), (5, 3), (9, 2)])
    x = bytestr([2, 42, 3, 101])
    WVPASSEQ(list(rpr(x)), [(0, 2)])


@wvtest
def test_uncache_ours_upto():
    history = []
    def mock_fadvise_done(f, ofs, len):
        history.append((f, ofs, len))

    uncache_upto = hashsplit._uncache_ours_upto
    page_size = os.sysconf("SC_PAGE_SIZE")
    old_fad = hashsplit.fadvise_done
    try:
        hashsplit.fadvise_done = mock_fadvise_done
        history = []
        uncache_upto('fd', 0, (0, 1), iter([]))
        WVPASSEQ([], history)
        uncache_upto('fd', page_size, (0, 1), iter([]))
        WVPASSEQ([('fd', 0, page_size)], history)
        history = []
        uncache_upto('fd', page_size, (0, 3), iter([(5, 2)]))
        WVPASSEQ([], history)
        uncache_upto('fd', 2 * page_size, (0, 3), iter([(5, 2)]))
        WVPASSEQ([], history)
        uncache_upto('fd', 3 * page_size, (0, 3), iter([(5, 2)]))
        WVPASSEQ([('fd', 0, 3 * page_size)], history)
        history = []
        uncache_upto('fd', 5 * page_size, (0, 3), iter([(5, 2)]))
        WVPASSEQ([('fd', 0, 3 * page_size)], history)
        history = []
        uncache_upto('fd', 6 * page_size, (0, 3), iter([(5, 2)]))
        WVPASSEQ([('fd', 0, 3 * page_size)], history)
        history = []
        uncache_upto('fd', 7 * page_size, (0, 3), iter([(5, 2)]))
        WVPASSEQ([('fd', 0, 3 * page_size),
                  ('fd', 5 * page_size, 2 * page_size)],
                 history)
    finally:
        hashsplit.fadvise_done = old_fad


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
