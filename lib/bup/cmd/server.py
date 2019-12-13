
import sys

from bup import options
from bup.io import byte_stream
from bup.server import BupServer
from bup.helpers import Conn, debug2


optspec = """
bup server
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    if extra:
        o.fatal('no arguments expected')

    debug2('bup server: reading from stdin.\n')

    with Conn(byte_stream(sys.stdin), byte_stream(sys.stdout)) as conn, \
         BupServer(conn) as server:
        server.handle()
