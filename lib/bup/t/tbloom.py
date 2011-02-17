import tempfile
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
    tf = tempfile.TemporaryFile()
    b = bloom.create('bup.bloom', f=tf, expected=2**28, delaywrite=False)
    WVPASSEQ(b.k, 4)
