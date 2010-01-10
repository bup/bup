#!/usr/bin/env python2.5
import sys, time
import options

optspec = """
bup tick
"""
o = options.Options('bup tick', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    log("bup tick: no arguments expected\n")
    o.usage()

t = time.time()
tleft = 1 - (t - int(t))
time.sleep(tleft)
