#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import sys

from bup import git, ls


git.check_repo_or_die()

# Check out lib/bup/ls.py for the opt spec
rc = ls.via_cmdline(sys.argv[1:])
sys.exit(rc)
