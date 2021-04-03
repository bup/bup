
from __future__ import absolute_import
import os, sys

from bup import options, _helpers
from bup.helpers import handle_ctrl_c, log, parse_num


optspec = """
bup random [-S seed] <numbytes>
--
S,seed=   optional random number seed [1]
f,force   print random data to stdout even if it's a tty
v,verbose print byte counter to stderr
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])

    if len(extra) != 1:
        o.fatal("exactly one argument expected")

    total = parse_num(extra[0])

    handle_ctrl_c()

    if opt.force or (not os.isatty(1) and
                     not int(os.environ.get('BUP_FORCE_TTY', 0)) & 1):
        _helpers.write_random(sys.stdout.fileno(), total, opt.seed,
                              opt.verbose and 1 or 0)
    else:
        log('error: not writing binary data to a terminal. Use -f to force.\n')
        sys.exit(1)
