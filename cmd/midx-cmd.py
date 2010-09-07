#!/usr/bin/env python
import sys, math, struct, glob, resource
from bup import options, git
from bup.helpers import *

PAGE_SIZE=4096
SHA_PER_PAGE=PAGE_SIZE/20.

optspec = """
bup midx [options...] <idxnames...>
--
o,output=  output midx filename (default: auto-generated)
a,auto     automatically create .midx from any unindexed .idx files
f,force    automatically create .midx from *all* .idx files
max-files= maximum number of idx files to open at once [-1]
dir=       directory containing idx/midx files
"""

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


def _do_midx(outdir, outfilename, infilenames):
    if not outfilename:
        assert(outdir)
        sum = Sha1('\0'.join(infilenames)).hexdigest()
        outfilename = '%s/midx-%s.midx' % (outdir, sum)
    
    inp = []
    total = 0
    allfilenames = {}
    for name in infilenames:
        ix = git.open_idx(name)
        for n in ix.idxnames:
            allfilenames[n] = 1
        inp.append(ix)
        total += len(ix)

    log('Merging %d indexes (%d objects).\n' % (len(infilenames), total))
    if (not opt.force and (total < 1024 and len(infilenames) < 3)) \
       or len(infilenames) < 2 \
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
        
    f.write('\0'.join(os.path.basename(p) for p in allfilenames.keys()))

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

    return total,outfilename


def do_midx(outdir, outfilename, infilenames):
    rv = _do_midx(outdir, outfilename, infilenames)
    if rv:
        print rv[1]


def do_midx_dir(path):
    already = {}
    sizes = {}
    if opt.force and not opt.auto:
        midxs = []   # don't use existing midx files
    else:
        midxs = glob.glob('%s/*.midx' % path)
        contents = {}
        for mname in midxs:
            m = git.open_idx(mname)
            contents[mname] = [('%s/%s' % (path,i)) for i in m.idxnames]
            sizes[mname] = len(m)
                    
        # sort the biggest midxes first, so that we can eliminate smaller
        # redundant ones that come later in the list
        midxs.sort(lambda x,y: -cmp(sizes[x], sizes[y]))
        
        for mname in midxs:
            any = 0
            for iname in contents[mname]:
                if not already.get(iname):
                    already[iname] = 1
                    any = 1
            if not any:
                log('%r is redundant\n' % mname)
                unlink(mname)
                already[mname] = 1

    midxs = [k for k in midxs if not already.get(k)]
    idxs = [k for k in glob.glob('%s/*.idx' % path) if not already.get(k)]

    for iname in idxs:
        i = git.open_idx(iname)
        sizes[iname] = len(i)

    all = [(sizes[n],n) for n in (midxs + idxs)]
    
    # FIXME: what are the optimal values?  Does this make sense?
    DESIRED_HWM = opt.force and 1 or 5
    DESIRED_LWM = opt.force and 1 or 2
    existed = dict((name,1) for sz,name in all)
    log('midx: %d indexes; want no more than %d.\n' % (len(all), DESIRED_HWM))
    if len(all) <= DESIRED_HWM:
        log('midx: nothing to do.\n')
    while len(all) > DESIRED_HWM:
        all.sort()
        part1 = [name for sz,name in all[:len(all)-DESIRED_LWM+1]]
        part2 = all[len(all)-DESIRED_LWM+1:]
        all = list(do_midx_group(path, part1)) + part2
        if len(all) > DESIRED_HWM:
            log('\nStill too many indexes (%d > %d).  Merging again.\n'
                % (len(all), DESIRED_HWM))

    for sz,name in all:
        if not existed.get(name):
            print name


def do_midx_group(outdir, infiles):
    for sublist in _group(infiles, opt.max_files):
        rv = _do_midx(path, None, sublist)
        if rv:
            yield rv



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
    if opt.dir:
        paths = [opt.dir]
    else:
        paths = [git.repo('objects/pack')]
        paths += glob.glob(git.repo('index-cache/*/.'))
    for path in paths:
        log('midx: scanning %s\n' % path)
        do_midx_dir(path)
        log('\n')
else:
    o.fatal("you must use -f or -a or provide input filenames")
