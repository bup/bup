
from collections import namedtuple
from os.path import abspath, basename, dirname, realpath
from shlex import quote
from subprocess import PIPE, check_output
from traceback import extract_stack
import errno, os, subprocess, sys, tempfile

from bup import helpers
from bup.compat import fsencode
from bup.io import enc_shs


def logcmd(cmd):
    def cvt(x):
        if isinstance(x, bytes):
            return enc_shs(x).decode('ascii')
        if isinstance(x, str):
            return enc_shs(x)
        assert False, x
    if isinstance(cmd, str):
        print(' '.join(cvt(x) for x in cmd), file=sys.stderr)

ex_res = namedtuple('SubprocResult', ('out', 'err', 'rc'))

def _normalize_cmd(cmd):
    assert cmd, cmd
    if not isinstance(cmd[0], (bytes, str)): # exc((arg, arg, ...), **kwds)
        assert len(cmd) == 1, cmd
        cmd = cmd[0]
    for arg in cmd:
        assert isinstance(arg, (bytes, str)), \
            f'{arg} is not bytes or str in {cmd}'
    return cmd

def exc(*args, **kwargs):
    """Print cmd to stderr and then run it via subprocess.run(), but
    with a default of check=True.  If the command's stderr is
    captured, and there's any data, write it to stderr.  Return a
    corresponding ex_res().

    Accepts both exc("echo", "x", ...) and exc(("echo", x"), ...),
    i.e. the first argument can be the entire command..

    """
    cmd = _normalize_cmd(args)
    logcmd(cmd)
    kwargs.setdefault('check', True)
    cp = subprocess.run(cmd, **kwargs)
    if cp.stderr:
        sys.stderr.flush()
        if isinstance(cp.stderr, bytes):
            sys.stderr.buffer.write(cp.stderr)
        else:
            sys.stderr.write(cp.stderr)
    return ex_res(out=cp.stdout, err=cp.stderr, rc=cp.returncode)

def exo(*args, **kwargs):
    """Print cmd to stderr and then run it via ex(cmd, stdout=PIPE,
    ...).  Return a corresponding ex_res().

    Accepts both exc("echo", "x", ...) and exc(("echo", x"), ...),
    i.e. the first argument can be the entire command..

    """
    if 'stdout' not in kwargs:
        kwargs['stdout'] = PIPE
    else:
        assert kwargs['stdout'] == PIPE, kwargs
    return exc(*args, **kwargs)
