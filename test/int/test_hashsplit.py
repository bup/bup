
from __future__ import absolute_import
from io import BytesIO
from binascii import unhexlify
import math, os

from wvpytest import *

from bup import hashsplit, _helpers
from bup._helpers import HashSplitter, RecordHashSplitter
from bup.hashsplit import BUP_BLOBBITS, fanout

# These test objects generate a number of least significant bits set
# to one according to their key.  Note that these were generated with
# a *fixed* algorithm (there's a bug in the level decision), so we
# need to adjust for that, but on the plus side we can use them to
# test different bits settings
split_test_objs = {
    13: unhexlify('ded8f1fcf2f45dfadf3458'),
    14: unhexlify('f287ffeeffe1f0e1fa77b1de1837'),
    15: unhexlify('878eb7a2e5baf7fcc8fcc58060ccdad5849b6e89'),
    16: unhexlify('e0e7fdb3e7a579'),
    17: unhexlify('e2ecf2fdb49f01'),
    18: unhexlify('caeadffeb1e68b'),
    19: unhexlify('f1fca9d9bfc9c0'),
    20: unhexlify('d6e8dbb8d9fec7'),
    21: unhexlify('7987fcbda4f27759'),
    22: unhexlify('f4dc926c62617af4'),
    23: unhexlify('edaef4e7f49fb6'),
    24: unhexlify('f1f6fef642ae74'),
    25: unhexlify('2b6470a19fe3d7ad8dd99e95b87b2c71afe47e09b698278771c095a2dfebe8'),
    26: unhexlify('f0aa9fa696bc0707'),
    27: unhexlify('94b053be6c02e1b93c7503e0e87d893495b3da9bc4f8e049140859e8270a8f6d'),
    29: unhexlify('e8985d2c9e26eb2b5a963cd27dc5dbd1bad8b681f43707f40feba5bfc5ef76984f74e1b800b6425be63993'),
}

def test_samples():
    for k in split_test_objs:

        # Verify that the k least significant bits are 1 and that
        # the next most significant bit is zero (i.e. that the
        # rollsum of the data matched what we expect for this k).
        rsum = _helpers.rollsum(split_test_objs[k])
        ones = (1 << k) - 1
        mask = (ones << 1) | 1
        WVPASSEQ(rsum & mask, ones)

        # Now check that for the test object a HashSplitter returns
        # the right level and split blob (which by construction should
        # be the input blob).
        #
        # The level should be the count of one bits more significant
        # than the "bits" value...
        exp_level = k - BUP_BLOBBITS
        # ...after ignoring the bit immediately "above" the 13'th bit
        # (quirk in the original algorithm -- see ./DESIGN).
        if exp_level > 0:
            exp_level -= 1
        hs = HashSplitter([BytesIO(split_test_objs[k])],
                          bits=BUP_BLOBBITS,
                          fanbits=1)
        blob, level = next(hs)
        WVPASSEQ(blob, split_test_objs[k])
        WVPASSEQ(level, exp_level)

def test_rolling_sums():
    WVPASS(_helpers.selftest())

def test_fanout_behaviour():
    for hashbits in 13, 14, 15:
        def sb(pfx, level):
            """Return tuple of split content and expected level (from table)."""
            needed = hashbits + hashsplit.fanbits() * level
            # internal algorithm ignores one bit after the split bits,
            # adjust for that (if n > 0):
            if level:
                needed += 1
            return b'\x00' * pfx + split_test_objs[needed], level
        def end(n):
            return b'\x00' * n, 0
        # check a given sequence is handled correctly
        def check(chunks_and_levels):
            data = b''.join([x[0] for x in chunks_and_levels])
            split = list(HashSplitter([BytesIO(data)], bits=hashbits,
                                      fanbits=hashsplit.fanbits()))
            WVPASSEQ(chunks_and_levels, split)

        old_fanout = hashsplit.fanout
        try:
            # cf. max_blob in _hashsplit.c
            max_blob = b'\x00' * (1 << hashbits + 2), 0
            for hashsplit.fanout in 2, 4:
                # never split - just max blobs
                check([max_blob] * 4)
                check([sb(0, 0)])
                check([max_blob, sb(1, 3), max_blob])
                check([sb(13, 1)])
                check([sb(13, 1), end(200)])
            hashsplit.fanout = 2
            check([sb(0, 1), sb(30, 2), sb(20, 0), sb(10, 5)])
            check([sb(0, 1), sb(30, 2), sb(20, 0), sb(10, 5), end(10)])
        finally:
            hashsplit.fanout = old_fanout

def test_hashsplit_files(tmpdir):
    # See HashSplitter_init for source of sizes
    blob_size = 1 << BUP_BLOBBITS
    max_blob_size = 1 << (BUP_BLOBBITS + 2)
    null_path = os.path.join(tmpdir, b'nulls')
    blobs_in_file = 10
    max_blob = bytearray(max_blob_size)
    with open(null_path, 'wb') as f:
        for idx in range(blobs_in_file):
            f.write(max_blob)
    max_blob = None

    with open(null_path, 'rb') as z0, \
         open(null_path, 'rb') as z1, \
         open(null_path, 'rb') as z2:
        res = [(len(b), lvl) for b, lvl in HashSplitter([z0, z1, z2],
                                                        bits=BUP_BLOBBITS)]
    WVPASSEQ(res, [(max_blob_size, 0)] * (blobs_in_file * 3))

    def split_bytes(n):
        return BytesIO(split_test_objs[n])
    def ex(n):
        fanout_bits = math.log(fanout, 2)
        # Add 1 because bup has always ignored one bit between the
        # blob bits and the fanout bits.
        return [(len(split_test_objs[n]),
                 (n - (BUP_BLOBBITS + 1)) // fanout_bits)]

    with open(null_path, 'rb') as z0, \
         open(null_path, 'rb') as z1:
        res = [(len(b), lvl) for b, lvl in HashSplitter([z0, split_bytes(14), z1],
                                                        bits=BUP_BLOBBITS)]
    WVPASSEQ(res, (blobs_in_file * [(max_blob_size, 0)]
                   + ex(14)
                   + blobs_in_file * [(max_blob_size, 0)]))

    res = [(len(b), lvl)
           for b, lvl in HashSplitter([split_bytes(14), split_bytes(15)],
                                      bits=BUP_BLOBBITS)]
    WVPASSEQ(res, ex(14) + ex(15))

    res = [(len(b), lvl)
           for b, lvl in HashSplitter([split_bytes(14), split_bytes(27)],
                                      bits=BUP_BLOBBITS)]
    WVPASSEQ(res, ex(14) + ex(27))
    os.remove(null_path)

def test_hashsplit_boundaries():
    # See HashSplitter_init for source of sizes
    blob_size = 1 << BUP_BLOBBITS
    max_blob_size = 1 << (BUP_BLOBBITS + 2)

    # Check keep_boundaries when the data has no split points
    def bio(s):
        return BytesIO(s)
    nulls = bytearray(blob_size)
    hs = HashSplitter([bio(nulls), bio(nulls), bio(nulls), bio(nulls)],
                      bits=BUP_BLOBBITS, keep_boundaries=False)
    res = [(len(b), lvl) for b, lvl in hs]
    WVPASSEQ(res, [(max_blob_size, 0)])

    hs = HashSplitter([bio(nulls), bio(nulls), bio(nulls), bio(nulls)],
                      bits=BUP_BLOBBITS)
    res = [(len(b), lvl) for b, lvl in hs]
    WVPASSEQ(res, 4 * [(blob_size, 0)])
    nulls = None

    # Check keep_boundaries when the data has internal split points
    def split_bytes(n):
        return BytesIO(split_test_objs[n])
    def ex(n):
        p = n
        # Subtract 1 because bup has always ignored one bit between
        # the blob bits and the fanout bits.
        if p > BUP_BLOBBITS: p -= 1
        fanout_bits = math.log(fanout, 2)
        return (len(split_test_objs[n]), (p - BUP_BLOBBITS) // fanout_bits)
    exp = [ex(13), ex(14), ex(15)]
    hs = HashSplitter([split_bytes(13), split_bytes(14), split_bytes(15)],
                      bits=BUP_BLOBBITS)
    res = [(len(b), lvl) for b, lvl in hs]
    WVPASSEQ(res, exp)

    hs = HashSplitter([split_bytes(13), split_bytes(14), split_bytes(15)],
                      bits=BUP_BLOBBITS, keep_boundaries=False)
    res = [(len(b), lvl) for b, lvl in hs]
    WVPASSEQ(res, exp)

    # Check keep_boundaries when the data has no internal split points
    data = split_test_objs[27]
    d1, d2 = data[:len(data) // 2], data[len(data) // 2:]

    hs = HashSplitter([bio(d1), bio(d2)], bits=BUP_BLOBBITS)
    res = [(len(b), lvl) for b, lvl in hs]
    WVPASSEQ(res, [(len(d1), 0), (len(d2), 0)])

    hs = HashSplitter([bio(d1), bio(d2)],
                      bits=BUP_BLOBBITS, keep_boundaries=False, fanbits=1)
    res = [(len(b), lvl) for b, lvl in hs]
    # Subtract 1 because bup has always ignored one bit between the
    # blob bits and the fanout bits.
    WVPASSEQ(res, [(len(data), 27 - BUP_BLOBBITS - 1)])

def test_hashsplitter_object():
    def _splitbuf(data):
        data = data[:]
        hs = HashSplitter([BytesIO(data)], bits=BUP_BLOBBITS, fanbits=1)
        sz = 0
        for blob, lvl in hs:
            # this isn't necessarily _quite_ right, but try to
            # reconstruct from a max blob to not having split
            if len(blob) == 4 << 13 and lvl == 0:
                sz += len(blob)
                continue
            yield sz + len(blob), 13 + lvl
            sz = 0
    def _splitbufHS(data):
        offs = None
        fed = 0
        data = data[:]
        s = RecordHashSplitter(bits=BUP_BLOBBITS)
        while offs != 0:
            while data:
                offs, bits = s.feed(data[:1])
                fed += 1
                if offs:
                    yield fed, bits
                    fed = 0
                data = data[1:]
        yield fed, 13
    data = b''.join([b'%d\n' % x for x in range(10000)])
    WVPASSEQ([x for x in _splitbuf(data)],
             [x for x in _splitbufHS(data)])
    data = b''.join([b'%.10x\n' % x for x in range(10000)])
    WVPASSEQ([x for x in _splitbuf(data)],
             [x for x in _splitbufHS(data)])
