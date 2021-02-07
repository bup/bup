
from __future__ import absolute_import
import os, glob, sys

from bup import options, path
from bup.compat import argv_bytes


optspec = """
bup help <command>
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])

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
