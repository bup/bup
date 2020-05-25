#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
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
