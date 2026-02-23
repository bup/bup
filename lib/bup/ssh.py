"""SSH connection.
Connect to a remote host via SSH and execute a command on the host.
"""

from os import environb as environ
from subprocess import PIPE, Popen
import re

from bup import path
from bup.compat import environ
from bup.io import buglvl, debug1


def connect(destination, port, subcmd, stderr=None):
    """Connect to the destination and execute the bup subcmd there.
    The destination is passed to ssh(1) as its destination argument.

    When BUP_TEST_LEVEL exists in the environment and the destination
    is false, or b'-', run the subcmd as a subprocess rather than via
    ssh.

    """
    assert not re.search(br'[^\w-]', subcmd)
    if not destination:
        if b'BUP_TEST_LEVEL' not in environ:
            raise Exception(f'no ssh destination')
        argv = [path.exe(), subcmd]
    elif destination == b'-':
        if b'BUP_TEST_LEVEL' not in environ:
            raise Exception(f'invalid ssh destination "-"')
        argv = [path.exe(), subcmd]
    else:
        force_tty = int(environ.get(b'BUP_FORCE_TTY', 0))
        argv = [b'ssh']
        if port:
            argv.extend((b'-p', port))
        argv.extend((destination, b'--',
                     b"sh -c 'BUP_DEBUG=%d BUP_FORCE_TTY=%d bup %s'"
                     % (buglvl, force_tty, subcmd)))
        debug1(f'ssh: {argv!r}\n')
    return Popen(argv, stdin=PIPE, stdout=PIPE, stderr=stderr,
                 start_new_session=True)
