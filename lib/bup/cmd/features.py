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

import platform

from bup import _helpers, compat, metadata, options, version
from bup.io import byte_stream

out = None

def show_support(out, bool_opt, what):
    out.write(b'    %s: %s\n' % (what, b'yes' if bool_opt else b'no'))

optspec = """
bup features
"""
o = options.Options(optspec)
opt, flags, extra = o.parse(compat.argv[1:])

sys.stdout.flush()
out = byte_stream(sys.stdout)

out.write(b'bup %s\n' % version.version)
out.write(b'Source %s %s\n' % (version.commit, version.date))

have_readline = getattr(_helpers, 'readline', None)
have_libacl = getattr(_helpers, 'read_acl', None)
have_xattr = metadata.xattr

out.write(b'    Python: %s\n' % platform.python_version().encode('ascii'))
show_support(out, have_readline, b'Command line editing (e.g. bup ftp)')
show_support(out, have_libacl, b'Saving and restoring POSIX ACLs')
show_support(out, have_xattr, b'Saving and restoring extended attributes (xattrs)')
