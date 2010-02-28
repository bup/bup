#!/usr/bin/env python
import sys, mmap
import options, _hashsplit
from helpers import *

optspec = """
bup random [-S seed] <numbytes>
--
S,seed=   optional random number seed (default 1)
"""
o = options.Options('bup random', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) != 1:
    o.fatal("exactly one argument expected")

total = parse_num(extra[0])
_hashsplit.write_random(sys.stdout.fileno(), total, opt.seed or 0)
