
from __future__ import absolute_import, print_function
import errno, platform, tempfile

from wvtest import *

from bup import bloom
from bup.helpers import mkdirp
from buptest import no_lingering_errors, test_tempdir


@wvtest
def test_bloom():
    with no_lingering_errors():
        with test_tempdir(b'bup-tbloom-') as tmpdir:
            hashes = [os.urandom(20) for i in range(100)]
            class Idx:
                pass
            ix = Idx()
            ix.name = b'dummy.idx'
            ix.shatable = b''.join(hashes)
            for k in (4, 5):
                b = bloom.create(tmpdir + b'/pybuptest.bloom', expected=100, k=k)
                b.add_idx(ix)
                WVPASSLT(b.pfalse_positive(), .1)
                b.close()
                b = bloom.ShaBloom(tmpdir + b'/pybuptest.bloom')
                all_present = True
                for h in hashes:
                    all_present &= (b.exists(h) or False)
                WVPASS(all_present)
                false_positives = 0
                for h in [os.urandom(20) for i in range(1000)]:
                    if b.exists(h):
                        false_positives += 1
                WVPASSLT(false_positives, 5)
                os.unlink(tmpdir + b'/pybuptest.bloom')

            tf = tempfile.TemporaryFile(dir=tmpdir)
            b = bloom.create(b'bup.bloom', f=tf, expected=100)
            WVPASSEQ(b.rwfile, tf)
            WVPASSEQ(b.k, 5)

            # Test large (~1GiB) filter.  This may fail on s390 (31-bit
            # architecture), and anywhere else where the address space is
            # sufficiently limited.
            tf = tempfile.TemporaryFile(dir=tmpdir)
            skip_test = False
            try:
                b = bloom.create(b'bup.bloom', f=tf, expected=2**28,
                                 delaywrite=False)
            except EnvironmentError as ex:
                (ptr_width, linkage) = platform.architecture()
                if ptr_width == '32bit' and ex.errno == errno.ENOMEM:
                    WVMSG('skipping large bloom filter test (mmap probably failed) '
                          + str(ex))
                    skip_test = True
                else:
                    raise
            if not skip_test:
                WVPASSEQ(b.k, 4)
