#!/usr/bin/env python
import sys, re, struct, mmap, time
from bup import git, options
from bup.helpers import *

handle_ctrl_c()

def s_from_bytes(bytes):
    clist = [chr(b) for b in bytes]
    return ''.join(clist)


last = start = 0
def report(count):
    global last, start
    fields = ['VmSize', 'VmRSS', 'VmData', 'VmStk', 'ms']
    d = {}
    for line in open('/proc/self/status').readlines():
        l = re.split(r':\s*', line.strip(), 1)
        d[l[0]] = l[1]
    now = time.time()
    d['ms'] = int((now - last) * 1000)
    if count >= 0:
        e1 = count
        fields = [d[k] for k in fields]
    else:
        e1 = ''
        start = now
    print ('%9s  ' + ('%10s ' * len(fields))) % tuple([e1] + fields)
    sys.stdout.flush()
    last = time.time()


optspec = """
bup memtest [-n elements] [-c cycles]
--
n,number=  number of objects per cycle [10000]
c,cycles=  number of cycles to run [100]
ignore-midx  ignore .midx files, use only .idx files
existing   test with existing objects instead of fake ones
"""
o = options.Options('bup memtest', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal('no arguments expected')

git.ignore_midx = opt.ignore_midx

git.check_repo_or_die()
m = git.PackIdxList(git.repo('objects/pack'))

report(-1)
f = open('/dev/urandom')
a = mmap.mmap(-1, 20)
report(0)

if opt.existing:
    def foreverit(mi):
        while 1:
            for e in mi:
                yield e
    objit = iter(foreverit(m))
    
for c in xrange(opt.cycles):
    for n in xrange(opt.number):
        if opt.existing:
            bin = objit.next()
            assert(m.exists(bin))
        else:
            b = f.read(3)
            a[0:2] = b[0:2]
            a[2] = chr(ord(b[2]) & 0xf0)
            bin = str(a[0:20])

            # technically, a randomly generated object id might exist.
            # but the likelihood of that is the likelihood of finding
            # a collision in sha-1 by accident, which is so unlikely that
            # we don't care.
            assert(not m.exists(bin))
    report((c+1)*opt.number)

print 'Total time: %.3fs' % (time.time() - start)
