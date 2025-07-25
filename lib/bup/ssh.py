"""SSH connection.
Connect to a remote host via SSH and execute a command on the host.
"""

from subprocess import PIPE, Popen
import re

from bup import path
from bup.compat import environ
from bup.io import buglvl, debug1


def connect(rhost, port, subcmd, stderr=None):
    """Connect to 'rhost' and execute the bup subcommand 'subcmd' on it."""
    assert not re.search(br'[^\w-]', subcmd)
    if rhost is None or rhost == b'-':
        argv = [path.exe(), subcmd]
    else:
        force_tty = int(environ.get(b'BUP_FORCE_TTY', 0))
        argv = [b'ssh']
        if port:
            argv.extend((b'-p', port))
        argv.extend((rhost, b'--',
                     b"sh -c 'BUP_DEBUG=%d BUP_FORCE_TTY=%d bup %s'"
                     % (buglvl, force_tty, subcmd)))
        debug1(f'ssh: {argv!r}\n')
    return Popen(argv, stdin=PIPE, stdout=PIPE, stderr=stderr,
                 start_new_session=True)
