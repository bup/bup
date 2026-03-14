

import sys

from bup import options
from bup.compat import argv_bytes
from bup.helpers import EXIT_FAILURE, EXIT_SUCCESS, linereader, log
from bup.io import byte_stream
from bup.repo import main_repo_location, repo_for_location


optspec = """
bup join [-r host:path] [refs or hashes...]
--
r,remote=  remote repository path
o=         output filename
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags_, extra = o.parse_bytes(argv[1:])
    loc = main_repo_location(argv_bytes(opt.remote) if opt.remote else None,
                             o.fatal)
    stdin = byte_stream(sys.stdin)
    if not extra:
        extra = linereader(stdin)

    with repo_for_location(loc) as src:
        if opt.o:
            outfile = open(opt.o, 'wb')
        else:
            sys.stdout.flush()
            outfile = byte_stream(sys.stdout)

        for ref in [argv_bytes(x) for x in extra]:
            try:
                for blob in src.join(ref):
                    outfile.write(blob)
            except KeyError as e:
                outfile.flush()
                log('error: %s\n' % e)
                return EXIT_FAILURE

    return EXIT_SUCCESS
