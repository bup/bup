
from __future__ import absolute_import, print_function
import os, time

from wvtest import *

from bup import index, metadata
from bup.compat import fsencode
from bup.helpers import mkdirp, resolve_parent
from buptest import no_lingering_errors, test_tempdir
import bup.xstat as xstat


lib_t_dir = os.path.dirname(fsencode(__file__))


@wvtest
def index_basic():
    with no_lingering_errors():
        cd = os.path.realpath(b'../')
        WVPASS(cd)
        sd = os.path.realpath(cd + b'/sampledata')
        WVPASSEQ(resolve_parent(cd + b'/sampledata'), sd)
        WVPASSEQ(os.path.realpath(cd + b'/sampledata/x'), sd + b'/x')
        WVPASSEQ(os.path.realpath(cd + b'/sampledata/var/abs-symlink'),
                 sd + b'/var/abs-symlink-target')
        WVPASSEQ(resolve_parent(cd + b'/sampledata/var/abs-symlink'),
                 sd + b'/var/abs-symlink')


@wvtest
def index_writer():
    with no_lingering_errors():
        with test_tempdir(b'bup-tindex-') as tmpdir:
            orig_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                ds = xstat.stat(b'.')
                fs = xstat.stat(lib_t_dir + b'/tindex.py')
                ms = index.MetaStoreWriter(b'index.meta.tmp');
                tmax = (time.time() - 1) * 10**9
                w = index.Writer(b'index.tmp', ms, tmax)
                w.add(b'/var/tmp/sporky', fs, 0)
                w.add(b'/etc/passwd', fs, 0)
                w.add(b'/etc/', ds, 0)
                w.add(b'/', ds, 0)
                ms.close()
                w.close()
            finally:
                os.chdir(orig_cwd)


def dump(m):
    for e in list(m):
        print('%s%s %s' % (e.is_valid() and ' ' or 'M',
                           e.is_fake() and 'F' or ' ',
                           e.name))

def fake_validate(*l):
    for i in l:
        for e in i:
            e.validate(0o100644, index.FAKE_SHA)
            e.repack()

def eget(l, ename):
    for e in l:
        if e.name == ename:
            return e

@wvtest
def index_negative_timestamps():
    with no_lingering_errors():
        with test_tempdir(b'bup-tindex-') as tmpdir:
            # Makes 'foo' exist
            foopath = tmpdir + b'/foo'
            f = open(foopath, 'wb')
            f.close()

            # Dec 31, 1969
            os.utime(foopath, (-86400, -86400))
            ns_per_sec = 10**9
            tmax = (time.time() - 1) * ns_per_sec
            e = index.BlankNewEntry(foopath, 0, tmax)
            e.update_from_stat(xstat.stat(foopath), 0)
            WVPASS(e.packed())

            # Jun 10, 1893
            os.utime(foopath, (-0x80000000, -0x80000000))
            e = index.BlankNewEntry(foopath, 0, tmax)
            e.update_from_stat(xstat.stat(foopath), 0)
            WVPASS(e.packed())


@wvtest
def index_dirty():
    with no_lingering_errors():
        with test_tempdir(b'bup-tindex-') as tmpdir:
            orig_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                default_meta = metadata.Metadata()
                ms1 = index.MetaStoreWriter(b'index.meta.tmp')
                ms2 = index.MetaStoreWriter(b'index2.meta.tmp')
                ms3 = index.MetaStoreWriter(b'index3.meta.tmp')
                meta_ofs1 = ms1.store(default_meta)
                meta_ofs2 = ms2.store(default_meta)
                meta_ofs3 = ms3.store(default_meta)

                ds = xstat.stat(lib_t_dir)
                fs = xstat.stat(lib_t_dir + b'/tindex.py')
                tmax = (time.time() - 1) * 10**9

                w1 = index.Writer(b'index.tmp', ms1, tmax)
                w1.add(b'/a/b/x', fs, meta_ofs1)
                w1.add(b'/a/b/c', fs, meta_ofs1)
                w1.add(b'/a/b/', ds, meta_ofs1)
                w1.add(b'/a/', ds, meta_ofs1)
                #w1.close()
                WVPASS()

                w2 = index.Writer(b'index2.tmp', ms2, tmax)
                w2.add(b'/a/b/n/2', fs, meta_ofs2)
                #w2.close()
                WVPASS()

                w3 = index.Writer(b'index3.tmp', ms3, tmax)
                w3.add(b'/a/c/n/3', fs, meta_ofs3)
                #w3.close()
                WVPASS()

                r1 = w1.new_reader()
                r2 = w2.new_reader()
                r3 = w3.new_reader()
                WVPASS()

                r1all = [e.name for e in r1]
                WVPASSEQ(r1all,
                         [b'/a/b/x', b'/a/b/c', b'/a/b/', b'/a/', b'/'])
                r2all = [e.name for e in r2]
                WVPASSEQ(r2all,
                         [b'/a/b/n/2', b'/a/b/n/', b'/a/b/', b'/a/', b'/'])
                r3all = [e.name for e in r3]
                WVPASSEQ(r3all,
                         [b'/a/c/n/3', b'/a/c/n/', b'/a/c/', b'/a/', b'/'])
                all = [e.name for e in index.merge(r2, r1, r3)]
                WVPASSEQ(all,
                         [b'/a/c/n/3', b'/a/c/n/', b'/a/c/',
                          b'/a/b/x', b'/a/b/n/2', b'/a/b/n/', b'/a/b/c',
                          b'/a/b/', b'/a/', b'/'])
                fake_validate(r1)
                dump(r1)

                print([hex(e.flags) for e in r1])
                WVPASSEQ([e.name for e in r1 if e.is_valid()], r1all)
                WVPASSEQ([e.name for e in r1 if not e.is_valid()], [])
                WVPASSEQ([e.name for e in index.merge(r2, r1, r3) if not e.is_valid()],
                         [b'/a/c/n/3', b'/a/c/n/', b'/a/c/',
                          b'/a/b/n/2', b'/a/b/n/', b'/a/b/', b'/a/', b'/'])

                expect_invalid = [b'/'] + r2all + r3all
                expect_real = (set(r1all) - set(r2all) - set(r3all)) \
                                | set([b'/a/b/n/2', b'/a/c/n/3'])
                dump(index.merge(r2, r1, r3))
                for e in index.merge(r2, r1, r3):
                    print(e.name, hex(e.flags), e.ctime)
                    eiv = e.name in expect_invalid
                    er  = e.name in expect_real
                    WVPASSEQ(eiv, not e.is_valid())
                    WVPASSEQ(er, e.is_real())
                fake_validate(r2, r3)
                dump(index.merge(r2, r1, r3))
                WVPASSEQ([e.name for e in index.merge(r2, r1, r3) if not e.is_valid()], [])

                e = eget(index.merge(r2, r1, r3), b'/a/b/c')
                e.invalidate()
                e.repack()
                dump(index.merge(r2, r1, r3))
                WVPASSEQ([e.name for e in index.merge(r2, r1, r3) if not e.is_valid()],
                         [b'/a/b/c', b'/a/b/', b'/a/', b'/'])
                w1.close()
                w2.close()
                w3.close()
            finally:
                os.chdir(orig_cwd)
