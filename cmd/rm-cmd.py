#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import sys

from bup.compat import argv_bytes
from bup.git import check_repo_or_die
from bup.options import Options
from bup.helpers import die_if_errors, handle_ctrl_c, log
from bup.repo import LocalRepo
from bup.rm import bup_rm

optspec = """
bup rm <branch|save...>
--
#,compress=  set compression level to # (0-9, 9 is highest) [6]
v,verbose    increase verbosity (can be specified multiple times)
unsafe       use the command even though it may be DANGEROUS
"""

handle_ctrl_c()

o = Options(optspec)
opt, flags, extra = o.parse(sys.argv[1:])

if not opt.unsafe:
    o.fatal('refusing to run dangerous, experimental command without --unsafe')

if len(extra) < 1:
    o.fatal('no paths specified')

check_repo_or_die()
repo = LocalRepo()
bup_rm(repo, [argv_bytes(x) for x in extra],
       compression=opt.compress, verbosity=opt.verbose)
die_if_errors()
