#!/usr/bin/env python
import sys, math, struct, glob, resource
from bup import options, git
from bup.helpers import *

PAGE_SIZE=4096
SHA_PER_PAGE=PAGE_SIZE/20.


def _group(l, count):
    for i in xrange(0, len(l), count):
        yield l[i:i+count]
        
        
def max_files():
    mf = min(resource.getrlimit(resource.RLIMIT_NOFILE))
    if mf > 32:
        mf -= 20  # just a safety margin
    else:
        mf -= 6   # minimum safety margin
    return mf


def merge(idxlist, bits, table):
    count = 0
    for e in git.idxmerge(idxlist):
        count += 1
        prefix = git.extract_bits(e, bits)
        table[prefix] = count
        yield e


def do_midx(outdir, outfilename, infilenames):
    if not outfilename:
        assert(outdir)
        sum = Sha1('\0'.join(infilenames)).hexdigest()
        outfilename = '%s/midx-%s.midx' % (outdir, sum)
    
    inp = []
    total = 0
    for name in infilenames:
        ix = git.PackIdx(name)
        inp.append(ix)
        total += len(ix)

    log('Merging %d indexes (%d objects).\n' % (len(infilenames), total))
    if (not opt.force and (total < 1024 and len(infilenames) < 3)) \
       or (opt.force and not total):
        log('midx: nothing to do.\n')
        return

    pages = int(total/SHA_PER_PAGE) or 1
    bits = int(math.ceil(math.log(pages, 2)))
    entries = 2**bits
    log('Table size: %d (%d bits)\n' % (entries*4, bits))
    
    table = [0]*entries

    try:
        os.unlink(outfilename)
    except OSError:
        pass
    f = open(outfilename + '.tmp', 'w+')
    f.write('MIDX\0\0\0\2')
    f.write(struct.pack('!I', bits))
    assert(f.tell() == 12)
    f.write('\0'*4*entries)
    
    for e in merge(inp, bits, table):
        f.write(e)
        
    f.write('\0'.join(os.path.basename(p) for p in infilenames))

    f.seek(12)
    f.write(struct.pack('!%dI' % entries, *table))
    f.close()
    os.rename(outfilename + '.tmp', outfilename)

    # this is just for testing
    if 0:
        p = git.PackMidx(outfilename)
        assert(len(p.idxnames) == len(infilenames))
        print p.idxnames
        assert(len(p) == total)
        pi = iter(p)
        for i in merge(inp, total, bits, table):
            assert(i == pi.next())
            assert(p.exists(i))

    print outfilename

optspec = """
bup midx [options...] <idxnames...>
--
o,output=  output midx filename (default: auto-generated)
a,auto     automatically create .midx from any unindexed .idx files
f,force    automatically create .midx from *all* .idx files
max-files= maximum number of idx files to open at once [-1]
"""
o = options.Options('bup midx', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra and (opt.auto or opt.force):
    o.fatal("you can't use -f/-a and also provide filenames")

git.check_repo_or_die()

if opt.max_files < 0:
    opt.max_files = max_files()
assert(opt.max_files >= 5)

if extra:
    do_midx(git.repo('objects/pack'), opt.output, extra)
elif opt.auto or opt.force:
    paths = [git.repo('objects/pack')]
    paths += glob.glob(git.repo('index-cache/*/.'))
    for path in paths:
        log('midx: scanning %s\n' % path)
        if opt.force:
            idxs = glob.glob('%s/*.idx' % path)
            for sublist in _group(idxs, opt.max_files):
                do_midx(path, opt.output, sublist)
        elif opt.auto:
            m = git.PackIdxList(path)
            needed = {}
            for pack in m.packs:  # only .idx files without a .midx are open
                if pack.name.endswith('.idx'):
                    needed[pack.name] = 1
            del m
            do_midx(path, opt.output, needed.keys())
        log('\n')
else:
    o.fatal("you must use -f or -a or provide input filenames")
