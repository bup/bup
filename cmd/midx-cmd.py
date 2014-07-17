#!/usr/bin/env python
import sys, math, struct, glob, resource
import tempfile
from bup import options, git, midx, _helpers, xstat
from bup.helpers import *

PAGE_SIZE=4096
SHA_PER_PAGE=PAGE_SIZE/20.

optspec = """
bup midx [options...] <idxnames...>
--
o,output=  output midx filename (default: auto-generated)
a,auto     automatically use all existing .midx/.idx files as input
f,force    merge produce exactly one .midx containing all objects
p,print    print names of generated midx files
check      validate contents of the given midx files (with -a, all midx files)
max-files= maximum number of idx files to open at once [-1]
d,dir=     directory containing idx/midx files
"""

merge_into = _helpers.merge_into


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


def check_midx(name):
    nicename = git.repo_rel(name)
    log('Checking %s.\n' % nicename)
    try:
        ix = git.open_idx(name)
    except git.GitError, e:
        add_error('%s: %s' % (name, e))
        return
    for count,subname in enumerate(ix.idxnames):
        sub = git.open_idx(os.path.join(os.path.dirname(name), subname))
        for ecount,e in enumerate(sub):
            if not (ecount % 1234):
                qprogress('  %d/%d: %s %d/%d\r' 
                          % (count, len(ix.idxnames),
                             git.shorten_hash(subname), ecount, len(sub)))
            if not sub.exists(e):
                add_error("%s: %s: %s missing from idx"
                          % (nicename, git.shorten_hash(subname),
                             str(e).encode('hex')))
            if not ix.exists(e):
                add_error("%s: %s: %s missing from midx"
                          % (nicename, git.shorten_hash(subname),
                             str(e).encode('hex')))
    prev = None
    for ecount,e in enumerate(ix):
        if not (ecount % 1234):
            qprogress('  Ordering: %d/%d\r' % (ecount, len(ix)))
        if not e >= prev:
            add_error('%s: ordering error: %s < %s'
                      % (nicename,
                         str(e).encode('hex'), str(prev).encode('hex')))
        prev = e


_first = None
def _do_midx(outdir, outfilename, infilenames, prefixstr):
    global _first
    if not outfilename:
        assert(outdir)
        sum = Sha1('\0'.join(infilenames)).hexdigest()
        outfilename = '%s/midx-%s.midx' % (outdir, sum)
    
    inp = []
    total = 0
    allfilenames = []
    midxs = []
    try:
        for name in infilenames:
            ix = git.open_idx(name)
            midxs.append(ix)
            inp.append((
                ix.map,
                len(ix),
                ix.sha_ofs,
                isinstance(ix, midx.PackMidx) and ix.which_ofs or 0,
                len(allfilenames),
            ))
            for n in ix.idxnames:
                allfilenames.append(os.path.basename(n))
            total += len(ix)
        inp.sort(lambda x,y: cmp(str(y[0][y[2]:y[2]+20]),str(x[0][x[2]:x[2]+20])))

        if not _first: _first = outdir
        dirprefix = (_first != outdir) and git.repo_rel(outdir)+': ' or ''
        debug1('midx: %s%screating from %d files (%d objects).\n'
               % (dirprefix, prefixstr, len(infilenames), total))
        if (opt.auto and (total < 1024 and len(infilenames) < 3)) \
           or ((opt.auto or opt.force) and len(infilenames) < 2) \
           or (opt.force and not total):
            debug1('midx: nothing to do.\n')
            return

        pages = int(total/SHA_PER_PAGE) or 1
        bits = int(math.ceil(math.log(pages, 2)))
        entries = 2**bits
        debug1('midx: table size: %d (%d bits)\n' % (entries*4, bits))

        unlink(outfilename)
        with atomically_replaced_file(outfilename, 'wb') as f:
            f.write('MIDX')
            f.write(struct.pack('!II', midx.MIDX_VERSION, bits))
            assert(f.tell() == 12)

            f.truncate(12 + 4*entries + 20*total + 4*total)
            f.flush()
            fdatasync(f.fileno())

            fmap = mmap_readwrite(f, close=False)

            count = merge_into(fmap, bits, total, inp)
            del fmap # Assume this calls msync() now.
            f.seek(0, os.SEEK_END)
            f.write('\0'.join(allfilenames))
    finally:
        for ix in midxs:
            if isinstance(ix, midx.PackMidx):
                ix.close()
        midxs = None
        inp = None


    # This is just for testing (if you enable this, don't clear inp above)
    if 0:
        p = midx.PackMidx(outfilename)
        assert(len(p.idxnames) == len(infilenames))
        print p.idxnames
        assert(len(p) == total)
        for pe, e in p, git.idxmerge(inp, final_progress=False):
            pin = pi.next()
            assert(i == pin)
            assert(p.exists(i))

    return total, outfilename


def do_midx(outdir, outfilename, infilenames, prefixstr):
    rv = _do_midx(outdir, outfilename, infilenames, prefixstr)
    if rv and opt['print']:
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
                    
        # sort the biggest+newest midxes first, so that we can eliminate
        # smaller (or older) redundant ones that come later in the list
        midxs.sort(key=lambda ix: (-sizes[ix], -xstat.stat(ix).st_mtime))
        
        for mname in midxs:
            any = 0
            for iname in contents[mname]:
                if not already.get(iname):
                    already[iname] = 1
                    any = 1
            if not any:
                debug1('%r is redundant\n' % mname)
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
    debug1('midx: %d indexes; want no more than %d.\n' 
           % (len(all), DESIRED_HWM))
    if len(all) <= DESIRED_HWM:
        debug1('midx: nothing to do.\n')
    while len(all) > DESIRED_HWM:
        all.sort()
        part1 = [name for sz,name in all[:len(all)-DESIRED_LWM+1]]
        part2 = all[len(all)-DESIRED_LWM+1:]
        all = list(do_midx_group(path, part1)) + part2
        if len(all) > DESIRED_HWM:
            debug1('\nStill too many indexes (%d > %d).  Merging again.\n'
                   % (len(all), DESIRED_HWM))

    if opt['print']:
        for sz,name in all:
            if not existed.get(name):
                print name


def do_midx_group(outdir, infiles):
    groups = list(_group(infiles, opt.max_files))
    gprefix = ''
    for n,sublist in enumerate(groups):
        if len(groups) != 1:
            gprefix = 'Group %d: ' % (n+1)
        rv = _do_midx(path, None, sublist, gprefix)
        if rv:
            yield rv


handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra and (opt.auto or opt.force):
    o.fatal("you can't use -f/-a and also provide filenames")
if opt.check and (not extra and not opt.auto):
    o.fatal("if using --check, you must provide filenames or -a")

git.check_repo_or_die()

if opt.max_files < 0:
    opt.max_files = max_files()
assert(opt.max_files >= 5)

if opt.check:
    # check existing midx files
    if extra:
        midxes = extra
    else:
        midxes = []
        paths = opt.dir and [opt.dir] or git.all_packdirs()
        for path in paths:
            debug1('midx: scanning %s\n' % path)
            midxes += glob.glob(os.path.join(path, '*.midx'))
    for name in midxes:
        check_midx(name)
    if not saved_errors:
        log('All tests passed.\n')
else:
    if extra:
        do_midx(git.repo('objects/pack'), opt.output, extra, '')
    elif opt.auto or opt.force:
        paths = opt.dir and [opt.dir] or git.all_packdirs()
        for path in paths:
            debug1('midx: scanning %s\n' % path)
            do_midx_dir(path)
    else:
        o.fatal("you must use -f or -a or provide input filenames")

if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    sys.exit(1)
