#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import, print_function
from os.path import relpath
import sys

from bup import options, drecurse
from bup.compat import argv_bytes
from bup.helpers import log, parse_excludes, parse_rx_excludes, saved_errors
from bup.io import byte_stream


optspec = """
bup drecurse <path>
--
x,xdev,one-file-system   don't cross filesystem boundaries
exclude= a path to exclude from the backup (can be used more than once)
exclude-from= a file that contains exclude paths (can be used more than once)
exclude-rx= skip paths matching the unanchored regex (may be repeated)
exclude-rx-from= skip --exclude-rx patterns in file (may be repeated)
q,quiet  don't actually print filenames
profile  run under the python profiler
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) != 1:
    o.fatal("exactly one filename expected")

drecurse_top = argv_bytes(extra[0])
excluded_paths = parse_excludes(flags, o.fatal)
if not drecurse_top.startswith(b'/'):
    excluded_paths = [relpath(x) for x in excluded_paths]
exclude_rxs = parse_rx_excludes(flags, o.fatal)
it = drecurse.recursive_dirlist([drecurse_top], opt.xdev,
                                excluded_paths=excluded_paths,
                                exclude_rxs=exclude_rxs)
if opt.profile:
    import cProfile
    def do_it():
        for i in it:
            pass
    cProfile.run('do_it()')
else:
    if opt.quiet:
        for i in it:
            pass
    else:
        sys.stdout.flush()
        out = byte_stream(sys.stdout)
        for (name,st) in it:
            out.write(name + b'\n')

if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    sys.exit(1)
