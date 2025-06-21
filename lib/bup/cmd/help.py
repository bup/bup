
import os, glob, sys

from bup import options, path
from bup.compat import argv_bytes
from bup.helpers import EXIT_FAILURE


optspec = """
bup help <command>
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])

    if len(extra) == 0:
        os.execvp(path.exe(), [path.exe(), b'-h'])
    elif len(extra) == 1:
        docname = (extra[0]=='bup' and b'bup' or (b'bup-%s' % argv_bytes(extra[0])))
        manpath = os.path.join(path.exedir(), b'../../Documentation/')
        dev_page = glob.glob(os.path.join(manpath, docname + b'.[1-9]'))
        try:
            if dev_page:
                os.environb[b'MANPATH'] = manpath
            os.execvp(b'man', [b'man', docname])
        except OSError as e:
            sys.stderr.write('Unable to run man command: %s\n' % e)
            sys.exit(EXIT_FAILURE)
    else:
        o.fatal("exactly one command name expected")
