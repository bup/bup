#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import sys

from bup import git, ls
from bup.io import byte_stream


git.check_repo_or_die()

sys.stdout.flush()
out = byte_stream(sys.stdout)
# Check out lib/bup/ls.py for the opt spec
rc = ls.via_cmdline(sys.argv[1:], out=out)
sys.exit(rc)
