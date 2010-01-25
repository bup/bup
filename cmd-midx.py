#!/usr/bin/env python
import sys, math, struct
import options, git
from helpers import *

PAGE_SIZE=4096
SHA_PER_PAGE=PAGE_SIZE/200.


def next(it):
    try:
        return it.next()
    except StopIteration:
        return None
    
    
optspec = """
bup midx -o outfile.midx <idxnames...>
--
o,output=  output midx file name
"""
o = options.Options('bup midx', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if not extra:
    log("bup midx: no input filenames given\n")
    o.usage()
if not opt.output:
    log("bup midx: no output filename given\n")
    o.usage()
    
inp = []
total = 0
for name in extra:
    ix = git.PackIndex(name)
    inp.append(ix)
    total += len(ix)
    
log('total objects expected: %d\n' % total)
pages = total/SHA_PER_PAGE
log('pages: %d\n' % pages)
bits = int(math.ceil(math.log(pages, 2)))
log('table bits: %d\n' % bits)
entries = 2**bits
log('table entries: %d\n' % entries)
log('table size: %d\n' % (entries*8))

table = [0]*entries

def merge(idxlist):
    iters = [iter(i) for i in inp]
    iters = [[next(it), it] for it in iters]
    count = 0
    while iters:
        if (count % 10000) == 0:
            log('\rMerging: %d/%d' % (count, total))
        e = min(iters)  # FIXME: very slow for long lists
        assert(e[0])
        yield e[0]
        count += 1
        prefix = git.extract_bits(e[0], bits)
        table[prefix] = count
        e[0] = next(e[1])
        iters = filter(lambda x: x[0], iters)
    log('\rMerging: done.                                    \n')

f = open(opt.output, 'w+')
f.write('MIDX\0\0\0\1')
f.write(struct.pack('!I', bits))
assert(f.tell() == 12)
f.write('\0'*8*entries)

for e in merge(inp):
    f.write(e)

f.write('\0'.join([os.path.basename(p) for p in extra]))

f.seek(12)
f.write(struct.pack('!%dQ' % entries, *table))
f.close()

# this is just for testing
if 0:
    p = git.PackMidx(opt.output)
    assert(len(p.idxnames) == len(extra))
    print p.idxnames
    assert(len(p) == total)
    pi = iter(p)
    for i in merge(inp):
        assert(i == pi.next())
        assert(p.exists(i))
