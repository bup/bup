#!/bin/sh
"""": # -*-python-*-
# https://sourceware.org/bugzilla/show_bug.cgi?id=26034
export "BUP_ARGV_0"="$0"
arg_i=1
for arg in "$@"; do
    export "BUP_ARGV_${arg_i}"="$arg"
    shift
    arg_i=$((arg_i + 1))
done
# Here to end of preamble replaced during install
bup_python="$(dirname "$0")/../../config/bin/python" || exit $?
exec "$bup_python" "$0"
"""
# end of bup preamble

from __future__ import absolute_import
import os, sys

sys.path[:0] = [os.path.dirname(os.path.realpath(__file__)) + '/..']

from bup import compat, options, _helpers
from bup.helpers import handle_ctrl_c, log, parse_num


optspec = """
bup random [-S seed] <numbytes>
--
S,seed=   optional random number seed [1]
f,force   print random data to stdout even if it's a tty
v,verbose print byte counter to stderr
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(compat.argv[1:])

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
