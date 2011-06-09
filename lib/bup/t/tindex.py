import os
import time
from bup import index
from bup.helpers import *
import bup.xstat as xstat
from wvtest import *

@wvtest
def index_basic():
    cd = os.path.realpath('../../../t')
    WVPASS(cd)
    sd = os.path.realpath(cd + '/sampledata')
    WVPASSEQ(index.realpath(cd + '/sampledata'), cd + '/sampledata')
    WVPASSEQ(os.path.realpath(cd + '/sampledata/x'), sd + '/x')
    WVPASSEQ(os.path.realpath(cd + '/sampledata/etc'), os.path.realpath('/etc'))
    WVPASSEQ(index.realpath(cd + '/sampledata/etc'), sd + '/etc')


@wvtest
def index_writer():
    unlink('index.tmp')
    ds = xstat.stat('.')
    fs = xstat.stat('tindex.py')
    w = index.Writer('index.tmp', time.time() - 1)
    w.add('/var/tmp/sporky', fs)
    w.add('/etc/passwd', fs)
    w.add('/etc/', ds)
    w.add('/', ds)
    w.close()


def dump(m):
    for e in list(m):
        print '%s%s %s' % (e.is_valid() and ' ' or 'M',
                           e.is_fake() and 'F' or ' ',
                           e.name)

def fake_validate(*l):
    for i in l:
        for e in i:
            e.validate(0100644, index.FAKE_SHA)
            e.repack()

def eget(l, ename):
    for e in l:
        if e.name == ename:
            return e

@wvtest
def index_negative_timestamps():
    # Makes 'foo' exist
    f = file('foo', 'wb')
    f.close()

    # Dec 31, 1969
    os.utime("foo", (-86400, -86400))
    now = time.time()
    e = index.BlankNewEntry("foo", now - 1)
    e.from_stat(xstat.stat("foo"), now)
    assert len(e.packed())
    WVPASS()

    # Jun 10, 1893
    os.utime("foo", (-0x80000000, -0x80000000))
    e = index.BlankNewEntry("foo", now - 1)
    e.from_stat(xstat.stat("foo"), now)
    assert len(e.packed())
    WVPASS()

    unlink('foo')


@wvtest
def index_dirty():
    unlink('index.tmp')
    unlink('index2.tmp')
    ds = xstat.stat('.')
    fs = xstat.stat('tindex.py')
    tmax = time.time() - 1
    
    w1 = index.Writer('index.tmp', tmax)
    w1.add('/a/b/x', fs)
    w1.add('/a/b/c', fs)
    w1.add('/a/b/', ds)
    w1.add('/a/', ds)
    #w1.close()
    WVPASS()

    w2 = index.Writer('index2.tmp', tmax)
    w2.add('/a/b/n/2', fs)
    #w2.close()
    WVPASS()

    w3 = index.Writer('index3.tmp', tmax)
    w3.add('/a/c/n/3', fs)
    #w3.close()
    WVPASS()

    r1 = w1.new_reader()
    r2 = w2.new_reader()
    r3 = w3.new_reader()
    WVPASS()

    r1all = [e.name for e in r1]
    WVPASSEQ(r1all,
             ['/a/b/x', '/a/b/c', '/a/b/', '/a/', '/'])
    r2all = [e.name for e in r2]
    WVPASSEQ(r2all,
             ['/a/b/n/2', '/a/b/n/', '/a/b/', '/a/', '/'])
    r3all = [e.name for e in r3]
    WVPASSEQ(r3all,
             ['/a/c/n/3', '/a/c/n/', '/a/c/', '/a/', '/'])
    all = [e.name for e in index.merge(r2, r1, r3)]
    WVPASSEQ(all,
             ['/a/c/n/3', '/a/c/n/', '/a/c/',
              '/a/b/x', '/a/b/n/2', '/a/b/n/', '/a/b/c',
              '/a/b/', '/a/', '/'])
    fake_validate(r1)
    dump(r1)

    print [hex(e.flags) for e in r1]
    WVPASSEQ([e.name for e in r1 if e.is_valid()], r1all)
    WVPASSEQ([e.name for e in r1 if not e.is_valid()], [])
    WVPASSEQ([e.name for e in index.merge(r2, r1, r3) if not e.is_valid()],
             ['/a/c/n/3', '/a/c/n/', '/a/c/',
              '/a/b/n/2', '/a/b/n/', '/a/b/', '/a/', '/'])

    expect_invalid = ['/'] + r2all + r3all
    expect_real = (set(r1all) - set(r2all) - set(r3all)) \
                    | set(['/a/b/n/2', '/a/c/n/3'])
    dump(index.merge(r2, r1, r3))
    for e in index.merge(r2, r1, r3):
        print e.name, hex(e.flags), e.ctime
        eiv = e.name in expect_invalid
        er  = e.name in expect_real
        WVPASSEQ(eiv, not e.is_valid())
        WVPASSEQ(er, e.is_real())
    fake_validate(r2, r3)
    dump(index.merge(r2, r1, r3))
    WVPASSEQ([e.name for e in index.merge(r2, r1, r3) if not e.is_valid()], [])
    
    e = eget(index.merge(r2, r1, r3), '/a/b/c')
    e.invalidate()
    e.repack()
    dump(index.merge(r2, r1, r3))
    WVPASSEQ([e.name for e in index.merge(r2, r1, r3) if not e.is_valid()],
             ['/a/b/c', '/a/b/', '/a/', '/'])
