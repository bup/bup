
from subprocess import PIPE
import getopt, os, signal, struct, subprocess, sys

from bup import options, ssh, path
from bup.compat import argv_bytes
from bup.helpers import DemuxConn, log
from bup.io import byte_stream


optspec = """
bup on <hostname> <index|save|split|get> ...
"""

def main(argv):
    o = options.Options(optspec, optfunc=getopt.getopt)
    opt, flags, extra = o.parse_bytes(argv[1:])
    if len(extra) < 2:
        o.fatal('must specify index, save, split, or get command')

    class SigException(Exception):
        def __init__(self, signum):
            self.signum = signum
            Exception.__init__(self, 'signal %d received' % signum)
    def handler(signum, frame):
        raise SigException(signum)

    remote = argv_bytes(extra[0]).split(b':')
    argv = [argv_bytes(x) for x in extra[1:]]

    if len(remote) == 1:
        hostname, port = (remote[0], None)
    else:
        hostname, port = remote

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)

    sys.stdout.flush()
    out = byte_stream(sys.stdout)

    try:
        sp = None
        p = None
        ret = 99
        p = ssh.connect(hostname, port, b'on--server', stderr=PIPE)
        try:
            argvs = b'\0'.join([b'bup'] + argv)
            p.stdin.write(struct.pack('!I', len(argvs)) + argvs)
            p.stdin.flush()
            sp = subprocess.Popen([path.exe(), b'server'],
                                  stdin=p.stdout, stdout=p.stdin)
            p.stdin.close()
            p.stdout.close()
            # Demultiplex remote client's stderr (back to stdout/stderr).
            with DemuxConn(p.stderr.fileno(), open(os.devnull, "wb")) as dmc:
                for line in iter(dmc.readline, b''):
                    out.write(line)
        finally:
            while 1:
                # if we get a signal while waiting, we have to keep waiting, just
                # in case our child doesn't die.
                try:
                    ret = p.wait()
                    if sp:
                        sp.wait()
                    break
                except SigException as e:
                    log('\nbup on: %s\n' % e)
                    os.kill(p.pid, e.signum)
                    ret = 84
    except SigException as e:
        if ret == 0:
            ret = 99
        log('\nbup on: %s\n' % e)

    sys.exit(ret)
