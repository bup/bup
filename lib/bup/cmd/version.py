
import re, sys

from bup import options, version
from bup.io import byte_stream

version_rx = re.compile(r'^[0-9]+\.[0-9]+(\.[0-9]+)?(-[0-9]+-g[0-9abcdef]+)?$')

optspec = """
bup version [--date|--commit]
--
date    display the date this version of bup was created
commit  display the git commit id of this version of bup
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])


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
