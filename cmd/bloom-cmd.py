#!/usr/bin/env python
import sys, glob, tempfile
from bup import options, git
from bup.helpers import *

optspec = """
bup bloom [options...]
--
o,output=  output bloom filename (default: auto-generated)
d,dir=     input directory to look for idx files (default: auto-generated)
k,hashes=  number of hash functions to use (4 or 5) (default: auto-generated)
c,check=   an idx file to check against an existing bloom filter
"""

def check_bloom(path, bloomfilename, idx):
    if not os.path.exists(bloomfilename):
        log("bloom: %s not found to check\n" % bloomfilename)
        return
    b = git.ShaBloom(bloomfilename)
    if not b.valid():
        log("bloom: %s could not be opened to check\n" % bloomfilename)
        return
    base = os.path.basename(idx)
    if base not in b.idxnames:
        log("bloom: filter does not contain %s, nothing to check\n" % idx)
        return
    if base == idx:
        idx = os.path.join(path, idx)
    log("bloom: checking %s" % idx)
    for objsha in git.open_idx(idx):
        if not b.exists(objsha):
            add_error("bloom: ERROR: %s missing from bloom" 
                      % str(objsha).encode('hex'))


def do_bloom(path, outfilename):
    b = None
    if os.path.exists(outfilename):
        b = git.ShaBloom(outfilename)
        if not b.valid():
            debug1("bloom: Existing invalid bloom found, regenerating.\n")
            b = None

    add = []
    rest = []
    add_count = 0
    rest_count = 0
    for name in glob.glob('%s/*.idx' % path):
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
        log("bloom: Nothing to do\n")
        return

    if b:
        if len(b) != rest_count:
            log("bloom: size %d != idx total %d, regenerating\n"
                    % (len(b), rest_count))
            b = None
        elif (b.bits < git.MAX_BLOOM_BITS and
              b.pfalse_positive(add_count) > git.MAX_PFALSE_POSITIVE):
            log("bloom: %d more entries => %.2f false positive, regenerating\n"
                    % (add_count, b.pfalse_positive(add_count)))
            b = None
        else:
            b = git.ShaBloom(outfilename, readwrite=True, expected=add_count)
    if not b: # Need all idxs to build from scratch
        add += rest
        add_count += rest_count
    del rest
    del rest_count

    msg = b is None and 'creating from' or 'adding'
    log('bloom: %s %d file%s (%d object%s).\n' % (msg, len(add),
                                                  len(add)!=1 and 's' or '',
                                                  add_count,
                                                  add_count!=1 and 's' or ''))

    tfname = None
    if b is None:
        tfname = os.path.join(path, 'bup.tmp.bloom')
        tf = open(tfname, 'w+')
        b = git.ShaBloom.create(tfname, f=tf, expected=add_count, k=opt.k)
    count = 0
    for name in add:
        ix = git.open_idx(name)
        progress('Writing bloom: %d/%d\r' % (count, len(add)))
        b.add_idx(ix)
        count += 1
    log('Writing bloom: %d/%d, done.\n' % (count, len(add)))

    if tfname:
        os.rename(tfname, outfilename)


handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal('no positional parameters expected')

git.check_repo_or_die()
bloompath = opt.dir or git.repo('objects/pack')

if not opt.output:
    assert(bloompath)
outfilename = opt.output or os.path.join(bloompath, 'bup.bloom')

if opt.check:
    check_bloom(bloompath, outfilename, opt.check)
else:
    if opt.k and opt.k not in (4,5):
        o.fatal('only k values of 4 and 5 are supported')

    do_bloom(bloompath, outfilename)

if saved_errors:
    log('WARNING: %d errors encountered during bloom.\n' % len(saved_errors))
    sys.exit(1)
    
