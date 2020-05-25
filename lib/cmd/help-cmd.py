#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import sys, os, glob
from bup import options, path

optspec = """
bup help <command>
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) == 0:
    # the wrapper program provides the default usage string
    os.execvp(path.exe(), ['bup'])
elif len(extra) == 1:
    docname = (extra[0]=='bup' and 'bup' or ('bup-%s' % extra[0]))
    manpath = os.path.join(path.exedir(),
                           'Documentation/' + docname + '.[1-9]')
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
