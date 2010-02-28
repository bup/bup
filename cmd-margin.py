#!/usr/bin/env python
import sys
import options, git, _hashsplit
from helpers import *


optspec = """
bup margin
"""
o = options.Options('bup margin', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal("no arguments expected")

git.check_repo_or_die()
#git.ignore_midx = 1

mi = git.MultiPackIndex(git.repo('objects/pack'))
last = '\0'*20
longmatch = 0
for i in mi:
    if i == last:
        continue
    #assert(str(i) >= last)
    pm = _hashsplit.bitmatch(last, i)
    longmatch = max(longmatch, pm)
    last = i
print longmatch
