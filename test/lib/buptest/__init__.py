
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

def exc(cmd, **kwargs):
    """Print cmd to stderr and then run it via subprocess.run(), but
    with a default of check=True.  If the command's stderr is
    captured, and there's any data, write it to stderr.  Return a
    corresponding ex_res().

    """
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

def exo(cmd, **kwargs):
    """Print cmd to stderr and then run it via ex(cmd, stdout=PIPE,
    ...).  Return a corresponding ex_res().

    """
    logcmd(cmd)
    if 'stdout' not in kwargs:
        kwargs['stdout'] = PIPE
    else:
        assert kwargs['stdout'] == PIPE, kwargs
    return exc(cmd, **kwargs)
