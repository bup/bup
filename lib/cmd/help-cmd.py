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

# Intentionally replace the dirname "$0" that python prepends
import os, sys
sys.path[0] = os.path.dirname(os.path.realpath(__file__)) + '/..'

import glob

from bup import compat, options, path
from bup.compat import argv_bytes


optspec = """
bup help <command>
"""
o = options.Options(optspec)
opt, flags, extra = o.parse(compat.argv[1:])

if len(extra) == 0:
    # the wrapper program provides the default usage string
    os.execvp(path.exe(), [b'bup'])
elif len(extra) == 1:
    docname = (extra[0]=='bup' and b'bup' or (b'bup-%s' % argv_bytes(extra[0])))
    manpath = os.path.join(path.exedir(),
                           b'../../Documentation/' + docname + b'.[1-9]')
    g = glob.glob(manpath)
    try:
        if g:
            os.execvp('man', ['man', '-l', g[0]])
        else:
            os.execvp('man', ['man', docname])
    except OSError as e:
        sys.stderr.write('Unable to run man command: %s\n' % e)
        sys.exit(1)
else:
    o.fatal("exactly one command name expected")
