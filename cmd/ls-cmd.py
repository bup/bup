#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

import sys

from bup import git, ls


git.check_repo_or_die()

# Check out lib/bup/ls.py for the opt spec
rc = ls.do_ls(sys.argv[1:], default='/', spec_prefix='bup ')
sys.exit(rc)
