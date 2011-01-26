"""SSH connection.
Connect to a remote host via SSH and execute a command on the host.
"""
import sys, os, re, subprocess
from bup import helpers, path


def connect(rhost, port, subcmd):
    """Connect to 'rhost' and execute the bup subcommand 'subcmd' on it."""
    assert(not re.search(r'[^\w-]', subcmd))
    nicedir = re.sub(r':', "_", path.exedir())
    if rhost == '-':
        rhost = None
    if not rhost:
        argv = ['bup', subcmd]
    else:
        # WARNING: shell quoting security holes are possible here, so we
        # have to be super careful.  We have to use 'sh -c' because
        # csh-derived shells can't handle PATH= notation.  We can't
        # set PATH in advance, because ssh probably replaces it.  We
        # can't exec *safely* using argv, because *both* ssh and 'sh -c'
        # allow shellquoting.  So we end up having to double-shellquote
        # stuff here.
        escapedir = re.sub(r'([^\w/])', r'\\\\\\\1', nicedir)
        buglvl = helpers.atoi(os.environ.get('BUP_DEBUG'))
        force_tty = helpers.atoi(os.environ.get('BUP_FORCE_TTY'))
        cmd = r"""
                   sh -c PATH=%s:'$PATH BUP_DEBUG=%s BUP_FORCE_TTY=%s bup %s'
               """ % (escapedir, buglvl, force_tty, subcmd)
        argv = ['ssh']
        if port:
            argv.extend(('-p', port))
        argv.extend((rhost, '--', cmd.strip()))
        #helpers.log('argv is: %r\n' % argv)
    def setup():
        # runs in the child process
        if not rhost:
            os.environ['PATH'] = ':'.join([nicedir,
                                           os.environ.get('PATH', '')])
        os.setsid()
    return subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            preexec_fn=setup)
