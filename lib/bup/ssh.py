"""SSH connection.
Connect to a remote host via SSH and execute a command on the host.
"""

from __future__ import absolute_import, print_function
import sys, os, re, subprocess

from bup import helpers, path
from bup.compat import environ

def connect(rhost, port, subcmd, stderr=None):
    """Connect to 'rhost' and execute the bup subcommand 'subcmd' on it."""
    assert not re.search(br'[^\w-]', subcmd)
    if rhost is None or rhost == b'-':
        argv = [path.exe(), subcmd]
    else:
        buglvl = helpers.atoi(environ.get(b'BUP_DEBUG'))
        force_tty = helpers.atoi(environ.get(b'BUP_FORCE_TTY'))
        cmd = b"""
                   sh -c 'BUP_DEBUG=%d BUP_FORCE_TTY=%d bup %s'
               """ % (buglvl, force_tty, subcmd)
        argv = [b'ssh']
        if port:
            argv.extend((b'-p', port))
        argv.extend((rhost, b'--', cmd.strip()))
        #helpers.log('argv is: %r\n' % argv)
    if sys.version_info[0] < 3:
        return subprocess.Popen(argv,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=stderr,
                                preexec_fn=lambda: os.setsid())
    else:
        return subprocess.Popen(argv,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=stderr,
                                start_new_session=True)
