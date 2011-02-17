#!/usr/bin/env python
import sys, glob, tempfile
from bup import options, git
from bup.helpers import *

optspec = """
bup bloom [options...]
--
o,output=  output bloom filename (default: auto)
d,dir=     input directory to look for idx files (default: auto)
k,hashes=  number of hash functions to use (4 or 5) (default: auto)
"""

_first = None
def do_bloom(path, outfilename):
    global _first
    if not outfilename:
        assert(path)
        outfilename = os.path.join(path, 'bup.bloom')

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
            log("bloom: size %d != idx total %d, regenerating\n"
                    % (len(b), rest_count))
            b = None
        elif (b.bits < git.MAX_BLOOM_BITS and
              b.pfalse_positive(add_count) > git.MAX_PFALSE_POSITIVE):
            log("bloom: regenerating: adding %d entries gives "
                "%.2f%% false positives.\n"
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
    if not _first: _first = path
    dirprefix = (_first != path) and git.repo_rel(path)+': ' or ''
    log('bloom: %s%s %d file%s (%d object%s).\n'
        % (dirprefix, msg,
           len(add), len(add)!=1 and 's' or '',
           add_count, add_count!=1 and 's' or ''))

    tfname = None
    if b is None:
        tfname = os.path.join(path, 'bup.tmp.bloom')
        tf = open(tfname, 'w+')
        b = git.ShaBloom.create(tfname, f=tf, expected=add_count, k=opt.k)
    count = 0
    icount = 0
    for name in add:
        ix = git.open_idx(name)
        qprogress('bloom: writing %.2f%% (%d/%d objects)\r' 
                  % (icount*100.0/add_count, icount, add_count))
        b.add_idx(ix)
        count += 1
        icount += len(ix)

    if tfname:
        os.rename(tfname, outfilename)


handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal('no positional parameters expected')

if opt.k and opt.k not in (4,5):
    o.fatal('only k values of 4 and 5 are supported')

git.check_repo_or_die()

paths = opt.dir and [opt.dir] or git.all_packdirs()
for path in paths:
    debug1('bloom: scanning %s\n' % path)
    do_bloom(path, opt.output)
