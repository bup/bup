#!/usr/bin/env python
import sys, struct
from bup import options, git, _helpers
from bup.helpers import *


optspec = """
bup margin
--
predict    Guess object offsets and report the maximum deviation
ignore-midx  Don't use midx files; use only plain pack idx files.
"""
o = options.Options('bup margin', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal("no arguments expected")

git.check_repo_or_die()
git.ignore_midx = opt.ignore_midx

mi = git.PackIdxList(git.repo('objects/pack'))

def do_predict(ix):
    total = len(ix)
    maxdiff = 0
    for count,i in enumerate(ix):
        prefix = struct.unpack('!Q', i[:8])[0]
        expected = prefix * total / (1<<64)
        diff = count - expected
        maxdiff = max(maxdiff, abs(diff))
    print '%d of %d (%.3f%%) ' % (maxdiff, len(ix), maxdiff*100.0/len(ix))
    sys.stdout.flush()
    assert(count+1 == len(ix))

if opt.predict:
    if opt.ignore_midx:
        for pack in mi.packs:
            do_predict(pack)
    else:
        do_predict(mi)
else:
    # default mode: find longest matching prefix
    last = '\0'*20
    longmatch = 0
    for i in mi:
        if i == last:
            continue
        #assert(str(i) >= last)
        pm = _helpers.bitmatch(last, i)
        longmatch = max(longmatch, pm)
        last = i
    print longmatch
