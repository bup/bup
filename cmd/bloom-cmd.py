#!/usr/bin/env python
import sys, glob, tempfile
from bup import options, git, bloom
from bup.helpers import *

optspec = """
bup bloom [options...]
--
ruin       ruin the specified bloom file (clearing the bitfield)
f,force    ignore existing bloom file and regenerate it from scratch
o,output=  output bloom filename (default: auto)
d,dir=     input directory to look for idx files (default: auto)
k,hashes=  number of hash functions to use (4 or 5) (default: auto)
c,check=   check the given .idx file against the bloom filter
"""


def ruin_bloom(bloomfilename):
    rbloomfilename = git.repo_rel(bloomfilename)
    if not os.path.exists(bloomfilename):
        log("%s\n" % bloomfilename)
        add_error("bloom: %s not found to ruin\n" % rbloomfilename)
        return
    b = bloom.ShaBloom(bloomfilename, readwrite=True, expected=1)
    b.map[16:16+2**b.bits] = '\0' * 2**b.bits


def check_bloom(path, bloomfilename, idx):
    rbloomfilename = git.repo_rel(bloomfilename)
    ridx = git.repo_rel(idx)
    if not os.path.exists(bloomfilename):
        log("bloom: %s: does not exist.\n" % rbloomfilename)
        return
    b = bloom.ShaBloom(bloomfilename)
    if not b.valid():
        add_error("bloom: %r is invalid.\n" % rbloomfilename)
        return
    base = os.path.basename(idx)
    if base not in b.idxnames:
        log("bloom: %s does not contain the idx.\n" % rbloomfilename)
        return
    if base == idx:
        idx = os.path.join(path, idx)
    log("bloom: bloom file: %s\n" % rbloomfilename)
    log("bloom:   checking %s\n" % ridx)
    for objsha in git.open_idx(idx):
        if not b.exists(objsha):
            add_error("bloom: ERROR: object %s missing" 
                      % str(objsha).encode('hex'))


_first = None
def do_bloom(path, outfilename):
    global _first
    b = None
    if os.path.exists(outfilename) and not opt.force:
        b = bloom.ShaBloom(outfilename)
        if not b.valid():
            debug1("bloom: Existing invalid bloom found, regenerating.\n")
            b = None

    add = []
    rest = []
    add_count = 0
    rest_count = 0
    for i,name in enumerate(glob.glob('%s/*.idx' % path)):
        progress('bloom: counting: %d\r' % i)
        ix = git.open_idx(name)
        ixbase = os.path.basename(name)
        if b and (ixbase in b.idxnames):
            rest.append(name)
            rest_count += len(ix)
        else:
            add.append(name)
            add_count += len(ix)
    total = add_count + rest_count

    if not add:
        debug1("bloom: nothing to do.\n")
        return

    if b:
        if len(b) != rest_count:
            debug1("bloom: size %d != idx total %d, regenerating\n"
                   % (len(b), rest_count))
            b = None
        elif (b.bits < bloom.MAX_BLOOM_BITS and
              b.pfalse_positive(add_count) > bloom.MAX_PFALSE_POSITIVE):
            debug1("bloom: regenerating: adding %d entries gives "
                   "%.2f%% false positives.\n"
                   % (add_count, b.pfalse_positive(add_count)))
            b = None
        else:
            b = bloom.ShaBloom(outfilename, readwrite=True, expected=add_count)
    if not b: # Need all idxs to build from scratch
        add += rest
        add_count += rest_count
    del rest
    del rest_count

    msg = b is None and 'creating from' or 'adding'
    if not _first: _first = path
    dirprefix = (_first != path) and git.repo_rel(path)+': ' or ''
    progress('bloom: %s%s %d file%s (%d object%s).\n'
        % (dirprefix, msg,
           len(add), len(add)!=1 and 's' or '',
           add_count, add_count!=1 and 's' or ''))

    tfname = None
    if b is None:
        tfname = os.path.join(path, 'bup.tmp.bloom')
        b = bloom.create(tfname, expected=add_count, k=opt.k)
    count = 0
    icount = 0
    for name in add:
        ix = git.open_idx(name)
        qprogress('bloom: writing %.2f%% (%d/%d objects)\r' 
                  % (icount*100.0/add_count, icount, add_count))
        b.add_idx(ix)
        count += 1
        icount += len(ix)

    # Currently, there's an open file object for tfname inside b.
    # Make sure it's closed before rename.
    b.close()

    if tfname:
        os.rename(tfname, outfilename)


handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal('no positional parameters expected')

git.check_repo_or_die()

if not opt.check and opt.k and opt.k not in (4,5):
    o.fatal('only k values of 4 and 5 are supported')

paths = opt.dir and [opt.dir] or git.all_packdirs()
for path in paths:
    debug1('bloom: scanning %s\n' % path)
    outfilename = opt.output or os.path.join(path, 'bup.bloom')
    if opt.check:
        check_bloom(path, outfilename, opt.check)
    elif opt.ruin:
        ruin_bloom(outfilename)
    else:
        do_bloom(path, outfilename)

if saved_errors:
    log('WARNING: %d errors encountered during bloom.\n' % len(saved_errors))
    sys.exit(1)
elif opt.check:
    log('All tests passed.\n')
