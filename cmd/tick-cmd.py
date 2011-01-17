#!/usr/bin/env python
import sys, time
from bup import options

optspec = """
bup tick
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal("no arguments expected")

t = time.time()
tleft = 1 - (t - int(t))
time.sleep(tleft)
