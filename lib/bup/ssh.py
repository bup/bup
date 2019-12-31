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
    nicedir = re.sub(b':', b'_', path.exedir())
    if rhost == b'-':
        rhost = None
    if not rhost:
        argv = [b'bup', subcmd]
    else:
        # WARNING: shell quoting security holes are possible here, so we
        # have to be super careful.  We have to use 'sh -c' because
        # csh-derived shells can't handle PATH= notation.  We can't
        # set PATH in advance, because ssh probably replaces it.  We
        # can't exec *safely* using argv, because *both* ssh and 'sh -c'
        # allow shellquoting.  So we end up having to double-shellquote
        # stuff here.
        escapedir = re.sub(br'([^\w/])', br'\\\\\\\1', nicedir)
        buglvl = helpers.atoi(environ.get(b'BUP_DEBUG'))
        force_tty = helpers.atoi(environ.get(b'BUP_FORCE_TTY'))
        cmd = b"""
                   sh -c PATH=%s:'$PATH BUP_DEBUG=%s BUP_FORCE_TTY=%s bup %s'
               """ % (escapedir, buglvl, force_tty, subcmd)
        argv = [b'ssh']
        if port:
            argv.extend((b'-p', port))
        argv.extend((rhost, b'--', cmd.strip()))
        #helpers.log('argv is: %r\n' % argv)
    if rhost:
        env = environ
    else:
        envpath = environ.get(b'PATH')
        env = environ.copy()
        env[b'PATH'] = nicedir if not envpath else nicedir + b':' + envpath
    if sys.version_info[0] < 3:
        return subprocess.Popen(argv,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=stderr,
                                env=env,
                                preexec_fn=lambda: os.setsid())
    else:
        return subprocess.Popen(argv,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=stderr,
                                env=env,
                                start_new_session=True)
