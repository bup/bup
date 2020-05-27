
from __future__ import absolute_import
from io import BytesIO

from wvtest import *

from bup import hashsplit, _helpers, helpers
from bup.compat import byte_int, bytes_from_uint
from buptest import no_lingering_errors


def nr_regions(x, max_count=None):
    return list(hashsplit._nonresident_page_regions(bytearray(x), 1, max_count))


@wvtest
def test_nonresident_page_regions():
    with no_lingering_errors():
        WVPASSEQ(nr_regions([]), [])
        WVPASSEQ(nr_regions([1]), [])
        WVPASSEQ(nr_regions([0]), [(0, 1)])
        WVPASSEQ(nr_regions([1, 0]), [(1, 1)])
        WVPASSEQ(nr_regions([0, 0]), [(0, 2)])
        WVPASSEQ(nr_regions([1, 0, 1]), [(1, 1)])
        WVPASSEQ(nr_regions([1, 0, 0]), [(1, 2)])
        WVPASSEQ(nr_regions([0, 1, 0]), [(0, 1), (2, 1)])
        WVPASSEQ(nr_regions([0, 0, 1, 1, 1, 0, 0, 0, 1, 0, 0]),
                 [(0, 2), (5, 3), (9, 2)])
        WVPASSEQ(nr_regions([2, 42, 3, 101]), [(0, 2)])
        # Test limit
        WVPASSEQ(nr_regions([0, 0, 0], None), [(0, 3)])
        WVPASSEQ(nr_regions([0, 0, 0], 1), [(0, 1), (1, 1), (2, 1)])
        WVPASSEQ(nr_regions([0, 0, 0], 2), [(0, 2), (2, 1)])
        WVPASSEQ(nr_regions([0, 0, 0], 3), [(0, 3)])
        WVPASSEQ(nr_regions([0, 0, 0], 4), [(0, 3)])
        WVPASSEQ(nr_regions([0, 0, 1], None), [(0, 2)])
        WVPASSEQ(nr_regions([0, 0, 1], 1), [(0, 1), (1, 1)])
        WVPASSEQ(nr_regions([0, 0, 1], 2), [(0, 2)])
        WVPASSEQ(nr_regions([0, 0, 1], 3), [(0, 2)])
        WVPASSEQ(nr_regions([1, 0, 0], None), [(1, 2)])
        WVPASSEQ(nr_regions([1, 0, 0], 1), [(1, 1), (2, 1)])
        WVPASSEQ(nr_regions([1, 0, 0], 2), [(1, 2)])
        WVPASSEQ(nr_regions([1, 0, 0], 3), [(1, 2)])
        WVPASSEQ(nr_regions([1, 0, 0, 0, 1], None), [(1, 3)])
        WVPASSEQ(nr_regions([1, 0, 0, 0, 1], 1), [(1, 1), (2, 1), (3, 1)])
        WVPASSEQ(nr_regions([1, 0, 0, 0, 1], 2), [(1, 2), (3, 1)])
        WVPASSEQ(nr_regions([1, 0, 0, 0, 1], 3), [(1, 3)])
        WVPASSEQ(nr_regions([1, 0, 0, 0, 1], 4), [(1, 3)])


@wvtest
def test_uncache_ours_upto():
    history = []
    def mock_fadvise_pages_done(f, ofs, len):
        history.append((f, ofs, len))

    with no_lingering_errors():
        uncache_upto = hashsplit._uncache_ours_upto
        page_size = helpers.sc_page_size
        orig_pages_done = hashsplit._fadvise_pages_done
        try:
            hashsplit._fadvise_pages_done = mock_fadvise_pages_done
            history = []
            uncache_upto(42, 0, (0, 1), iter([]))
            WVPASSEQ([], history)
            uncache_upto(42, page_size, (0, 1), iter([]))
            WVPASSEQ([(42, 0, 1)], history)
            history = []
            uncache_upto(42, page_size, (0, 3), iter([(5, 2)]))
            WVPASSEQ([], history)
            uncache_upto(42, 2 * page_size, (0, 3), iter([(5, 2)]))
            WVPASSEQ([], history)
            uncache_upto(42, 3 * page_size, (0, 3), iter([(5, 2)]))
            WVPASSEQ([(42, 0, 3)], history)
            history = []
            uncache_upto(42, 5 * page_size, (0, 3), iter([(5, 2)]))
            WVPASSEQ([(42, 0, 3)], history)
            history = []
            uncache_upto(42, 6 * page_size, (0, 3), iter([(5, 2)]))
            WVPASSEQ([(42, 0, 3)], history)
            history = []
            uncache_upto(42, 7 * page_size, (0, 3), iter([(5, 2)]))
            WVPASSEQ([(42, 0, 3), (42, 5, 2)], history)
        finally:
            hashsplit._fadvise_pages_done = orig_pages_done


@wvtest
def test_rolling_sums():
    with no_lingering_errors():
        WVPASS(_helpers.selftest())

@wvtest
def test_fanout_behaviour():

    # Drop in replacement for bupsplit, but splitting if the int value of a
    # byte >= BUP_BLOBBITS
    basebits = _helpers.blobbits()
    def splitbuf(buf):
        ofs = 0
        for b in buf:
            b = byte_int(b)
            ofs += 1
            if b >= basebits:
                return ofs, b
        return 0, 0

    with no_lingering_errors():
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
        z = lambda n: b'\x00' * n
        # Return a byte which will be split with a level of n
        sb = lambda n: bytes_from_uint(basebits + n)

        split_never = BytesIO(z(16))
        split_first = BytesIO(z(1) + sb(3) + z(14))
        split_end   = BytesIO(z(13) + sb(1) + z(2))
        split_many  = BytesIO(sb(1) + z(3) + sb(2) + z(4) +
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
