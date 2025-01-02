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

from __future__ import absolute_import, print_function
import os.path, sys

sys.path[:0] = [os.path.dirname(os.path.realpath(__file__)) + '/..']

from bup import compat, git, options
from bup.gc import bup_gc
from bup.helpers import die_if_errors, handle_ctrl_c, log


optspec = """
bup gc [options...]
--
v,verbose   increase log output (can be used more than once)
threshold=  only rewrite a packfile if it's over this percent garbage [10]
#,compress= set compression level to # (0-9, 9 is highest) [1]
unsafe      use the command even though it may be DANGEROUS
"""

# FIXME: server mode?
# FIXME: make sure client handles server-side changes reasonably

handle_ctrl_c()

print("""

WARNING: all versions of bup gc before 0.33.5 can produce saves with
missing objects (incomplete trees or commits).  See the 0.33.5 release
notes (note/0.33.5-from-0.33.4.md) in more recent versions for
additional information and ways to determine if you've been affected.
Refusing to run.  Please upgrade.

""".strip(),
      file=sys.stderr)

sys.exit(2)

o = options.Options(optspec)
opt, flags, extra = o.parse(compat.argv[1:])

if not opt.unsafe:
    o.fatal('refusing to run dangerous, experimental command without --unsafe')

if extra:
    o.fatal('no positional parameters expected')

if opt.threshold:
    try:
        opt.threshold = int(opt.threshold)
    except ValueError:
        o.fatal('threshold must be an integer percentage value')
    if opt.threshold < 0 or opt.threshold > 100:
        o.fatal('threshold must be an integer percentage value')

git.check_repo_or_die()

bup_gc(threshold=opt.threshold,
       compression=opt.compress,
       verbosity=opt.verbose)

die_if_errors()
