import errno, platform, tempfile
from bup import bloom
from bup.helpers import *
from wvtest import *

@wvtest
def test_bloom():
    hashes = [os.urandom(20) for i in range(100)]
    class Idx:
        pass
    ix = Idx()
    ix.name='dummy.idx'
    ix.shatable = ''.join(hashes)
    for k in (4, 5):
        b = bloom.create('pybuptest.bloom', expected=100, k=k)
        b.add_idx(ix)
        WVPASSLT(b.pfalse_positive(), .1)
        b.close()
        b = bloom.ShaBloom('pybuptest.bloom')
        all_present = True
        for h in hashes:
            all_present &= b.exists(h)
        WVPASS(all_present)
        false_positives = 0
        for h in [os.urandom(20) for i in range(1000)]:
            if b.exists(h):
                false_positives += 1
        WVPASSLT(false_positives, 5)
        os.unlink('pybuptest.bloom')

    tf = tempfile.TemporaryFile()
    b = bloom.create('bup.bloom', f=tf, expected=100)
    WVPASSEQ(b.rwfile, tf)
    WVPASSEQ(b.k, 5)

    # Test large (~1GiB) filter.  This may fail on s390 (31-bit
    # architecture), and anywhere else where the address space is
    # sufficiently limited.
    tf = tempfile.TemporaryFile()
    skip_test = False
    try:
        b = bloom.create('bup.bloom', f=tf, expected=2**28, delaywrite=False)
    except EnvironmentError, ex:
        (ptr_width, linkage) = platform.architecture()
        if ptr_width == '32bit' and ex.errno == errno.ENOMEM:
            WVMSG('skipping large bloom filter test (mmap probably failed) '
                  + str(ex))
            skip_test = True
        else:
            raise
    if not skip_test:
        WVPASSEQ(b.k, 4)
