
from binascii import hexlify
from subprocess import PIPE, Popen
# Python upstream deprecated this and then undeprecated it...
# pylint: disable-next=deprecated-module
import getopt
import os, struct, sys

from bup import git, options, ssh, protocol
from bup.cmd.save import opts_from_cmdline as parse_save_args
from bup.cmd.split import opts_from_cmdline as parse_split_args
from bup.compat import argv_bytes
from bup.git import check_repo_or_die, parse_commit
from bup.helpers import Conn, stopped
from bup.io import path_msg as pm
from bup.protocol import CommandDenied
from bup.repo import LocalRepo
import bup.cmd.save, bup.cmd.split, bup.path

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

def run_server(on_srv, config):
    class ServerRepo(LocalRepo):
        def __init__(self, repo_dir, server):
            self.closed = True # subclass' __del__ can run before its init
            git.check_repo_or_die(repo_dir)
            LocalRepo.__init__(self, repo_dir, server=server)
    with Conn(on_srv.stdout, on_srv.stdin) as conn, \
         protocol.Server(conn, ServerRepo, **config) as server:
        server.handle()

def restricted_repo_config():
    repo = git.repo()
    def init_dir(repo_, path):
        if not os.path.samefile(path, repo):
            raise CommandDenied(f'disallowing unexpected init-dir {pm(path)}')
    def set_dir(repo_, path):
        if not os.path.samefile(path, repo):
            raise CommandDenied(f'disallowing unexpected set-dir {pm(path)}')
    return {'vet_init_dir': init_dir, 'vet_set_dir': set_dir}

def save_or_split_server_config(argv, opt_parser):
    cmd = pm(argv[0])
    opt = opt_parser(argv)[0]
    def vet_update_ref(repo, ref, new_oid, prev_oid):
        # Ensure split/save adds only a new commit, with prev_oid (if
        # any) as its parent.
        cd = CommandDenied
        if ref != b'refs/heads/' + opt.name:
            raise cd(f'unexpected {cmd} ref update: {pm(ref)}')
        _, prev_kind, _, it = repo.cat(hexlify(prev_oid))
        if it:
            for _ in it: pass
        if prev_kind not in (None,  b'commit'):
            raise cd(f'{cmd}: existing {pm(ref)} {prev_oid.hex()} is not a commit')
        _, kind, _, it = repo.cat(hexlify(new_oid))
        if kind != b'commit':
            raise cd(f'{cmd}: {pm(ref)} update {new_oid.hex()} is not a commit')
        info = parse_commit(b''.join(it))
        if prev_kind and hexlify(prev_oid) not in info.parents:
            raise cd(f'{cmd}: {pm(ref)} update {new_oid.hex()} is not child of {prev_oid.hex()}')
    return {'commands': (b'config-get',
                         b'read-ref',
                         b'receive-objects-v2',
                         b'update-ref'),
            'vet_update_ref': vet_update_ref,
            **restricted_repo_config()}

def main(argv):
    o = options.Options(optspec, optfunc=getopt.getopt)
    extra = o.parse_bytes(argv[1:])[2]
    if len(extra) < 2:
        o.fatal('must specify a command to run on the host')
    dest, *argv = [argv_bytes(x) for x in extra]
    dest, colon, port = dest.rpartition(b':')
    if not colon:
        dest, port = port, None

    cmd = argv[0]
    if cmd == b'init':
        o.fatal('init is not supported; ssh or run "bup init -r ..." instead')
    if cmd in (b'features', b'help', b'index', b'version'):
        srv_config = None
    else:
        check_repo_or_die()
        if cmd == b'restore':
            srv_config = {'commands': (b'cat-batch', b'config-get',
                                       b'list-indexes', b'resolve'),
                          **restricted_repo_config()}
        elif cmd == b'get':
            srv_config = {'commands': 'all', **restricted_repo_config()}
        elif cmd == b'save':
            srv_config = save_or_split_server_config(argv, parse_save_args)
        elif cmd == b'split':
            srv_config = save_or_split_server_config(argv, parse_split_args)
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
            if srv_config:
                run_server(on_srv, srv_config)
            demux.wait() # finish the output
    return on_srv.returncode
