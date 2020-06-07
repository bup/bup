#!/bin/sh
"""": # -*-python-*-
# https://sourceware.org/bugzilla/show_bug.cgi?id=26034
export "BUP_ARGV_0"="$0"
arg_i=1
for arg in "$@"; do
    export "BUP_ARGV_${arg_i}"="$arg"
    shift
    arg_i=$((arg_i + 1))
done
# Here to end of preamble replaced during install
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0"
"""
# end of bup preamble

from __future__ import absolute_import
import sys, os, random

from bup import compat, options
from bup.compat import argv_bytes, bytes_from_uint, range
from bup.helpers import log
from bup.io import path_msg


def randblock(n):
    return b''.join(bytes_from_uint(random.randrange(0,256)) for i in range(n))


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
opt, flags, extra = o.parse(compat.argv[1:])

if not extra:
    o.fatal('filenames expected')

if opt.seed != None:
    random.seed(opt.seed)

for name in extra:
    name = argv_bytes(name)
    log('Damaging "%s"...\n' % path_msg(name))
    with open(name, 'r+b') as f:
        st = os.fstat(f.fileno())
        size = st.st_size
        if opt.percent or opt.size:
            ms1 = int(float(opt.percent or 0)/100.0*size) or size
            ms2 = opt.size or size
            maxsize = min(ms1, ms2)
        else:
            maxsize = 1
        chunks = opt.num or 10
        chunksize = size // chunks
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
