"""SSH connection.
Connect to a remote host via SSH and execute a command on the host.
"""

import re, subprocess

from bup import path
from bup.compat import environ

def connect(rhost, port, subcmd, stderr=None):
    """Connect to 'rhost' and execute the bup subcommand 'subcmd' on it."""
    assert not re.search(br'[^\w-]', subcmd)
    if rhost is None or rhost == b'-':
        argv = [path.exe(), subcmd]
    else:
        buglvl = int(environ.get(b'BUP_DEBUG', 0))
        force_tty = int(environ.get(b'BUP_FORCE_TTY', 0))
        tty_width = environ.get(b'BUP_TTY_WIDTH', None)
        if tty_width is not None:
            tty_width = b'BUP_TTY_WIDTH=%d' % int(tty_width)
        else:
            tty_width = b''
        cmd = b"""
                   sh -c 'BUP_DEBUG=%d BUP_FORCE_TTY=%d %s bup %s'
               """ % (buglvl, force_tty, tty_width, subcmd)
        argv = [b'ssh']
        if port:
            argv.extend((b'-p', port))
        argv.extend((rhost, b'--', cmd.strip()))
        #helpers.log('argv is: %r\n' % argv)
    return subprocess.Popen(argv,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=stderr,
                            start_new_session=True)
