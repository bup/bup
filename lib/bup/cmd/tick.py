
from __future__ import absolute_import
import os, sys, time

from bup import options


optspec = """
bup tick
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])

    if extra:
        o.fatal("no arguments expected")

    t = time.time()
    tleft = 1 - (t - int(t))
    time.sleep(tleft)
