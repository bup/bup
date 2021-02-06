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
bup_python="$(dirname "$0")/../../../config/bin/python" || exit $?
exec "$bup_python" "$0"
"""
# end of bup preamble

from __future__ import absolute_import, print_function

# Intentionally replace the dirname "$0" that python prepends
import os, sys
sys.path[0] = os.path.dirname(os.path.realpath(__file__)) + '/../..'

import re

from bup import compat, options, version
from bup.io import byte_stream

version_rx = re.compile(r'^[0-9]+\.[0-9]+(\.[0-9]+)?(-[0-9]+-g[0-9abcdef]+)?$')

optspec = """
bup version [--date|--commit]
--
date    display the date this version of bup was created
commit  display the git commit id of this version of bup
"""
o = options.Options(optspec)
opt, flags, extra = o.parse(compat.argv[1:])


total = (opt.date or 0) + (opt.commit or 0)
if total > 1:
    o.fatal('at most one option expected')

sys.stdout.flush()
out = byte_stream(sys.stdout)

if opt.date:
    out.write(version.date.split(b' ')[0] + b'\n')
elif opt.commit:
    out.write(version.commit + b'\n')
else:
    out.write(version.version + b'\n')
