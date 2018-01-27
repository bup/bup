#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import os, sys

from bup import options, _helpers
from bup.helpers import atoi, handle_ctrl_c, log, parse_num


optspec = """
bup random [-S seed] <numbytes>
--
S,seed=   optional random number seed [1]
f,force   print random data to stdout even if it's a tty
v,verbose print byte counter to stderr
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) != 1:
    o.fatal("exactly one argument expected")

total = parse_num(extra[0])

handle_ctrl_c()

if opt.force or (not os.isatty(1) and
                 not atoi(os.environ.get('BUP_FORCE_TTY')) & 1):
    _helpers.write_random(sys.stdout.fileno(), total, opt.seed,
                          opt.verbose and 1 or 0)
else:
    log('error: not writing binary data to a terminal. Use -f to force.\n')
    sys.exit(1)
