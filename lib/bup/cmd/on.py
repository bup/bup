
from subprocess import PIPE, Popen
# Python upstream deprecated this and then undeprecated it...
# pylint: disable-next=deprecated-module
import getopt
import struct, sys

from bup import git, options, ssh, protocol
from bup.compat import argv_bytes
from bup.helpers import Conn, stopped
from bup.io import path_msg as pm
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

def run_server(on_srv):
    class ServerRepo(LocalRepo):
        def __init__(self, repo_dir, server):
            self.closed = True # subclass' __del__ can run before its init
            git.check_repo_or_die(repo_dir)
            LocalRepo.__init__(self, repo_dir, server=server)
    with Conn(on_srv.stdout, on_srv.stdin) as conn, \
         protocol.Server(conn, ServerRepo) as server:
        server.handle()

def main(argv):
    o = options.Options(optspec, optfunc=getopt.getopt)
    extra = o.parse_bytes(argv[1:])[2]
    if len(extra) < 2:
        o.fatal('must specify index, save, split, or get command')
    dest, *argv = [argv_bytes(x) for x in extra]
    dest, colon, port = dest.rpartition(b':')
    if not colon:
        dest, port = port, None
    cmd = argv[0]
    if cmd == b'init':
        o.fatal('init is not supported; ssh or run "bup init -r ..." instead')
    if cmd in (b'features', b'help', b'index', b'version'):
        want_server = False
    elif cmd in (b'get', b'restore', b'save', b'split'):
        want_server = True
    else:
        o.fatal(f'{pm(cmd)} is not currently supported')
        assert False # (so pylint won't think srv_config might be unset)
    sys.stdout.flush()
    sys.stderr.flush()
    with ssh.connect(dest, port, b'on--server', stderr=PIPE) as on_srv:
        argvs = b'\0'.join([b'bup'] + argv)
        on_srv.stdin.write(struct.pack('!I', len(argvs)) + argvs)
        on_srv.stdin.flush()
        # write on--server's stdout/stderr to our stdout/stderr via demux
        with stopped(Popen((bup.path.exe(), b'demux'), stdin=on_srv.stderr),
                     timeout=1) as demux:
            if want_server:
                run_server(on_srv)
            demux.wait() # finish the output
    return on_srv.returncode
