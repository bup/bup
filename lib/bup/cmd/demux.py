
import os, sys

from bup import options
from bup.helpers import DemuxConn
from bup.io import byte_stream, path_msg as pm


optspec = """
bup demux # internal command (may be removed or changed at any time)
--
"""

def main(argv):
    o = options.Options(optspec)
    extra = o.parse_bytes(argv[1:])[2]
    if extra:
        o.fatal(f'unexpected arguments: {" ".join(pm(x) for x in extra)}')
    sys.stdout.flush()
    sys.stderr.flush()
    out = byte_stream(sys.stdout)
    try:
        with DemuxConn(sys.stdin.fileno(), open(os.devnull, "wb")) as dmc:
            for line in iter(dmc.readline, b''):
                out.write(line)
    finally: # just in case
        out.flush()
        sys.stderr.flush()
