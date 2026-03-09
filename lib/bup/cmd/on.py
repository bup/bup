
from subprocess import PIPE, Popen
# Python upstream deprecated this and then undeprecated it...
# pylint: disable-next=deprecated-module
import getopt
import struct, sys

from bup import git, options, ssh, protocol
from bup.compat import argv_bytes
from bup.helpers import Conn, stopped
from bup.repo import LocalRepo
import bup.path

optspec = """
bup on <[user@]host[:port]> <index|save|split|get> ...
"""

# Run the given given command on the host via ssh while reproducing
# its stdout, stderr, and exit status locally by multiplexing its
# stdout and stderr over the ssh connections stderr, and
# demultiplexing that back to the local stdout/stderr via bup-demux
# like so ("on" is this process, i.e. running the bup server via
# main() below):
#
#             +----------+
# stdin ----> |    on    | --- stdout -----------------+-----> local stdout
#             | (server) | --- stderr -----------------|-+---> local stderr
#             +----------+                             | |
#                    |  ^                              | |
#                    |  |                              | |
#                    |  |                              | |
#                    |  |                              | |
#                    |  |                              | |
#                    |  |                              | |
#    +-- ssh stdin --+  |                              | |
#    | (server input)   |                              | |
#    |                  |                              | |
#    | +-- ssh stdout --+                              | |
#    | | (server output)                               | |
#    | |                                               | |
#    | |                       +-------+ --- stdout ---+ |
#    | |   +--- ssh stderr --->| demux | --- stderr -----+
#    | |   |   (mux out/err)   +-------+
#    | |   |
#    v |   |
#  +------------------+
#  |   on--server     |
#  | (index/save/...) |
#  +------------------+
#

def main(argv):
    o = options.Options(optspec, optfunc=getopt.getopt)
    extra = o.parse_bytes(argv[1:])[2]
    if len(extra) < 2:
        o.fatal('must specify index, save, split, or get command')
    dest, *argv = [argv_bytes(x) for x in extra]
    dest, colon, port = dest.rpartition(b':')
    if not colon:
        dest, port = port, None
    sys.stdout.flush()
    sys.stderr.flush()
    with ssh.connect(dest, port, b'on--server', stderr=PIPE) as on_srv:
        argvs = b'\0'.join([b'bup'] + argv)
        on_srv.stdin.write(struct.pack('!I', len(argvs)) + argvs)
        on_srv.stdin.flush()

        class ServerRepo(LocalRepo):
            def __init__(self, repo_dir, server):
                self.closed = True # subclass' __del__ can run before its init
                git.check_repo_or_die(repo_dir)
                LocalRepo.__init__(self, repo_dir, server=server)

        # write on--server's stdout/stderr to our stdout/stderr via demux
        with stopped(Popen((bup.path.exe(), b'demux'), stdin=on_srv.stderr), 1) as demux, \
             Conn(on_srv.stdout, on_srv.stdin) as conn, \
             protocol.Server(conn, ServerRepo) as server:
            server.handle()
            demux.wait() # finish the output
    return on_srv.returncode
