"""SSH connection.
Connect to a remote host via SSH and execute a command on the host.
"""

from os import environb as environ
from subprocess import PIPE, Popen
import re

from bup import path
from bup.compat import environ
from bup.helpers import quote
from bup.io import buglvl, debug1


def connect(destination, port, subcmd, stderr=None):
    """Connect to the destination and execute the bup subcmd there.
    The destination is passed to ssh(1) as its destination argument.

    When BUP_TEST_LEVEL exists in the environment and the destination
    is false, or b'-', run the subcmd as a subprocess rather than via
    ssh, and choose bup as BUP_TEST_SSH_BUP_PATH when set or
    path.exe() (the current bup).

    When there is a destination, choose bup as BUP_TEST_SSH_BUP_PATH
    when set and BUP_TEST_LEVEL exists in the environment, otherwise
    "bup".

    The BUP_TEST_LEVEL arrangements are to allow testing without
    needing localhost ssh access, and to allow testing against some
    other "remote" bup.

    """
    assert re.fullmatch(br'[-_a-zA-Z0-9]+', subcmd), subcmd

    if not destination:
        if b'BUP_TEST_LEVEL' not in environ:
            raise Exception('no ssh destination')
        argv = [environ.get(b'BUP_TEST_SSH_BUP_PATH', path.exe()), subcmd]
    elif destination == b'-':
        if b'BUP_TEST_LEVEL' not in environ:
            raise Exception('invalid ssh destination "-"')
        argv = [environ.get(b'BUP_TEST_SSH_BUP_PATH', path.exe()), subcmd]
    else:
        bup = environ.get(b'BUP_TEST_SSH_BUP_PATH')
        if bup and b'BUP_TEST_LEVEL' not in environ:
            raise Exception('BUP_TEST_SSH_BUP_PATH only allowed when testing')
        bup = bup or b'bup'
        force_tty = int(environ.get(b'BUP_FORCE_TTY', 0))
        argv = [b'ssh']
        if port:
            argv.extend((b'-p', port))
        argv.extend((destination, b'--',
                     b"sh -c \"BUP_DEBUG=%d BUP_FORCE_TTY=%d %s %s\""
                     % (buglvl, force_tty, quote(bup), subcmd)))
        debug1(f'ssh: {argv!r}\n')
    return Popen(argv, stdin=PIPE, stdout=PIPE, stderr=stderr,
                 start_new_session=True)
