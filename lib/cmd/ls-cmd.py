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
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0"
"""
# end of bup preamble

from __future__ import absolute_import
import sys

from bup import compat, git, ls
from bup.io import byte_stream


git.check_repo_or_die()

sys.stdout.flush()
out = byte_stream(sys.stdout)
# Check out lib/bup/ls.py for the opt spec
rc = ls.via_cmdline(compat.argv[1:], out=out)
sys.exit(rc)
