#!/usr/bin/env python
import sys, mmap
from bup import options, _hashsplit
from bup.helpers import *

optspec = """
bup random [-S seed] <numbytes>
--
S,seed=   optional random number seed (default 1)
f,force   print random data to stdout even if it's a tty
"""
o = options.Options('bup random', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) != 1:
    o.fatal("exactly one argument expected")

total = parse_num(extra[0])

if opt.force or (not os.isatty(1) and
                 not atoi(os.environ.get('BUP_FORCE_TTY')) & 1):
    _hashsplit.write_random(sys.stdout.fileno(), total, opt.seed or 0)
else:
    log('error: not writing binary data to a terminal. Use -f to force.\n')
    sys.exit(1)
