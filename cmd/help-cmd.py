#!/usr/bin/env python
import sys, os, glob
from bup import options

optspec = """
bup help <command>
"""
o = options.Options('bup help', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) == 0:
    # the wrapper program provides the default usage string
    os.execvp(os.environ['BUP_MAIN_EXE'], ['bup'])
elif len(extra) == 1:
    docname = (extra[0]=='bup' and 'bup' or ('bup-%s' % extra[0]))
    exe = sys.argv[0]
    (exepath, exefile) = os.path.split(exe)
    manpath = os.path.join(exepath, '../Documentation/' + docname + '.[1-9]')
    g = glob.glob(manpath)
    if g:
        os.execvp('man', ['man', '-l', g[0]])
    else:
        os.execvp('man', ['man', docname])
else:
    o.fatal("exactly one command name expected")
