

import sys

from bup import options
from bup.compat import argv_bytes
from bup.config import derive_repo_addr
from bup.helpers import linereader, log
from bup.io import byte_stream
from bup.repo import make_repo


optspec = """
bup join [-r host:path] [refs or hashes...]
--
r,remote=  remote repository path
o=         output filename
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    addr = derive_repo_addr(remote=argv_bytes(opt.remote) if opt.remote else None,
                            die=o.fatal)

    stdin = byte_stream(sys.stdin)
    if not extra:
        extra = linereader(stdin)

    ret = 0
    with make_repo(addr) as repo:
        if opt.o:
            outfile = open(opt.o, 'wb')
        else:
            sys.stdout.flush()
            outfile = byte_stream(sys.stdout)

        for ref in [argv_bytes(x) for x in extra]:
            try:
                for blob in repo.join(ref):
                    outfile.write(blob)
            except KeyError as e:
                outfile.flush()
                log('error: %s\n' % e)
                ret = 1

    sys.exit(ret)
