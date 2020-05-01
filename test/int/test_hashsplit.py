
from __future__ import absolute_import
from io import BytesIO
import math
from binascii import unhexlify
import os

from wvpytest import *

from bup import hashsplit, _helpers
from bup._helpers import HashSplitter
from bup.hashsplit import BUP_BLOBBITS

# these test objects generate a # of bits per their key
# Note that these were generated with a *fixed* algorithm
# (there's a bug in the level decision), so we need to
# adjust for that, but on the plus side we can use them
# to test different bits settings
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
        if k <= 21:
            # First check that they have the right number of bits.
            rsum = _helpers.rollsum(split_test_objs[k])
            mask = (1 << (k + 1)) - 1
            ones = (1 << k) - 1
            WVPASSEQ(rsum & mask, ones)

        # then also check that again, with the default (bits=13)
        expected = k - 13
        # algorithm ignores 1 bit after the split bits
        if expected > 0:
            expected -= 1
        hs = HashSplitter([BytesIO(split_test_objs[k])],
                          bits=BUP_BLOBBITS,
                          fanbits=1)
        blob, level = next(hs)
        res = (k, len(blob), level)
        WVPASSEQ(res, (k, len(split_test_objs[k]), expected))

def test_rolling_sums():
    WVPASS(_helpers.selftest())

def test_fanout_behaviour():
    old_fanout = hashsplit.fanout

    global hashbits

    levels = lambda data: [(len(b), l) for b, l in
        hashsplit.hashsplit_iter([BytesIO(data)], True, None)]
    def hslevels(data):
        global hashbits
        return [(len(b), l) for b, l in
            HashSplitter([BytesIO(data)], bits=hashbits,
                         fanbits=int(math.log(hashsplit.fanout, 2)))]
    # This is a tuple of max blob size (4 << 13 bytes) and expected level (0)
    # Return tuple with split content and expected level (from table)
    def sb(pfx, n):
        needed = hashbits + int(math.log(hashsplit.fanout, 2)) * n
        # internal algorithm ignores one bit after the split bits,
        # adjust for that (if n > 0):
        if n:
            needed += 1
        return (b'\x00' * pfx + split_test_objs[needed], n)
    def end(n):
        return (b'\x00' * n, 0)

    # check a given sequence is handled correctly
    def check(objs):
        # old API allows only hashbits == 13
        if hashbits == 13:
            WVPASSEQ(levels(b''.join([x[0] for x in objs])), [(len(x[0]), x[1]) for x in objs])
        WVPASSEQ(hslevels(b''.join([x[0] for x in objs])), [(len(x[0]), x[1]) for x in objs])

    for hashbits in (13, 14, 15):
        max_blob = (b'\x00' * (4 << hashbits), 0)
        for hashsplit.fanout in (2, 4):
            # never split - just max blobs
            check([max_blob] * 4)
            check([sb(0, 0)])
            check([max_blob, sb(1, 3), max_blob])
            check([sb(13, 1)])
            check([sb(13, 1), end(200)])
        hashsplit.fanout = 2
        check([sb(0, 1), sb(30, 2), sb(20, 0), sb(10, 5)])
        check([sb(0, 1), sb(30, 2), sb(20, 0), sb(10, 5), end(10)])

    hashsplit.fanout = old_fanout

def test_hashsplit_files(tmpdir):
    fn = os.path.join(tmpdir, b'f1')
    f = open(fn, 'wb')
    sz = 0
    for idx in range(10):
        f.write(b'\x00' * 8192 * 4)
        sz += 4 * 8192
    f.close()
    def o():
        return open(fn, 'rb')
    res = [(len(b), lvl) for b, lvl in HashSplitter([o(), o(), o()],
                                                    bits=BUP_BLOBBITS)]
    WVPASSEQ(res, [(32*1024, 0)] * 10 * 3)

    def bio(n):
        return BytesIO(split_test_objs[n])
    def ex(n):
        return [(len(split_test_objs[n]), (n - 14) // 4)]

    res = [(len(b), lvl) for b, lvl in HashSplitter([o(), bio(14), o()],
                                                    bits=BUP_BLOBBITS)]
    WVPASSEQ(res, 10 * [(32*1024, 0)] + ex(14) + 10 * [(32*1024, 0)])

    res = [(len(b), lvl) for b, lvl in HashSplitter([bio(14), bio(15)],
                                                    bits=BUP_BLOBBITS)]
    WVPASSEQ(res, ex(14) + ex(15))

    res = [(len(b), lvl) for b, lvl in HashSplitter([bio(14), bio(27)],
                                                    bits=BUP_BLOBBITS)]
    WVPASSEQ(res, ex(14) + ex(27))

def test_hashsplit_boundaries():
    # check with/without boundaries and not finding any split points
    def bio(s):
        return BytesIO(s)
    hs = HashSplitter([bio(b'\x00' * 8192),
                       bio(b'\x00' * 8192),
                       bio(b'\x00' * 8192),
                       bio(b'\x00' * 8192)],
                      bits=BUP_BLOBBITS, keep_boundaries=False)
    res = [(len(b), lvl) for b, lvl in hs]
    WVPASSEQ(res, [(4*8192, 0)])

    hs = HashSplitter([bio(b'\x00' * 8192),
                       bio(b'\x00' * 8192),
                       bio(b'\x00' * 8192),
                       bio(b'\x00' * 8192)],
                      bits=BUP_BLOBBITS)
    res = [(len(b), lvl) for b, lvl in hs]
    WVPASSEQ(res, 4 * [(8192, 0)])

    # check with/without boundaries with split points
    def sbio(n):
        return BytesIO(split_test_objs[n])
    def ex(n):
        p = n
        if p > 13: p -= 1
        return (len(split_test_objs[n]), (p - 13) // 4)

    exp = [ex(13), ex(14), ex(15)]
    inputs = [sbio(13), sbio(14), sbio(15)]
    hs = HashSplitter(inputs, bits=BUP_BLOBBITS)
    res = [(len(b), lvl) for b, lvl in hs]
    WVPASSEQ(res, exp)
    inputs = [sbio(13), sbio(14), sbio(15)]
    hs = HashSplitter(inputs, bits=BUP_BLOBBITS,
                      keep_boundaries=False)
    res = [(len(b), lvl) for b, lvl in hs]
    WVPASSEQ(res, exp)

    # check with/without boundaries with found across boundary
    data = split_test_objs[27]
    d1, d2 = data[:len(data) // 2], data[len(data) // 2:]

    hs = HashSplitter([BytesIO(d1), BytesIO(d2)],
                      bits=BUP_BLOBBITS)
    res = [(len(b), lvl) for b, lvl in hs]
    WVPASSEQ(res, [(len(d1), 0), (len(d2), 0)])

    hs = HashSplitter([BytesIO(d1), BytesIO(d2)],
                      bits=BUP_BLOBBITS,
                      keep_boundaries=False, fanbits=1)
    res = [(len(b), lvl) for b, lvl in hs]
    WVPASSEQ(res, [(len(data), 27 - 13 - 1)])
