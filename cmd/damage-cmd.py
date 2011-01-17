#!/usr/bin/env python
import sys, os, random
from bup import options
from bup.helpers import *


def randblock(n):
    l = []
    for i in xrange(n):
        l.append(chr(random.randrange(0,256)))
    return ''.join(l)


optspec = """
bup damage [-n count] [-s maxsize] [-S seed] <filenames...>
--
   WARNING: THIS COMMAND IS EXTREMELY DANGEROUS
n,num=   number of blocks to damage
s,size=  maximum size of each damaged block
percent= maximum size of each damaged block (as a percent of entire file)
equal    spread damage evenly throughout the file
S,seed=  random number seed (for repeatable tests)
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if not extra:
    o.fatal('filenames expected')

if opt.seed != None:
    random.seed(opt.seed)

for name in extra:
    log('Damaging "%s"...\n' % name)
    f = open(name, 'r+b')
    st = os.fstat(f.fileno())
    size = st.st_size
    if opt.percent or opt.size:
        ms1 = int(float(opt.percent or 0)/100.0*size) or size
        ms2 = opt.size or size
        maxsize = min(ms1, ms2)
    else:
        maxsize = 1
    chunks = opt.num or 10
    chunksize = size/chunks
    for r in range(chunks):
        sz = random.randrange(1, maxsize+1)
        if sz > size:
            sz = size
        if opt.equal:
            ofs = r*chunksize
        else:
            ofs = random.randrange(0, size - sz + 1)
        log('  %6d bytes at %d\n' % (sz, ofs))
        f.seek(ofs)
        f.write(randblock(sz))
    f.close()
