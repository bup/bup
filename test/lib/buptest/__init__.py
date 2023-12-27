
from __future__ import absolute_import, print_function
from collections import namedtuple
from contextlib import contextmanager
from os.path import abspath, basename, dirname, realpath
from subprocess import PIPE, Popen
from traceback import extract_stack
import errno, os, subprocess, sys, tempfile

from bup import helpers
from bup.compat import fsencode, quote, str_type
from bup.io import byte_stream


ex_res = namedtuple('SubprocResult', ['out', 'err', 'proc', 'rc'])

def run(cmd, check=True, input=None, **kwargs):
    """Run a subprocess as per subprocess.Popen(cmd, **kwargs) followed by
    communicate(input=input).  If check is true, then throw an
    exception if the subprocess exits with non-zero status.  Return a
    SubprocResult tuple.

    """
    if input:
        assert 'stdin' not in kwargs
        kwargs['stdin'] = PIPE
    p = Popen(cmd, **kwargs)
    out, err = p.communicate(input=input)
    if check and p.returncode != 0:
        raise Exception('subprocess %r failed with status %d%s'
                        % (cmd, p.returncode,
                           (', stderr: %r' % err) if err else ''))
    return ex_res(out=out, err=err, proc=p, rc=p.returncode)

def logcmd(cmd):
    s = helpers.shstr(cmd)
    if isinstance(cmd, str_type):
        print(s, file=sys.stderr)
    else:
        # bytes - for now just escape it
        print(s.decode(errors='backslashreplace'), file=sys.stderr)

def ex(cmd, **kwargs):
    """Print cmd to stderr and then run it as per ex(...).
    Print the subprocess stderr to stderr if stderr=PIPE and there's
    any data.
    """
    logcmd(cmd)
    result = run(cmd, **kwargs)
    if result.err:
        sys.stderr.flush()
        byte_stream(sys.stderr).write(result.err)
    return result

def exo(cmd, **kwargs):
    """Print cmd to stderr and then run it as per ex(..., stdout=PIPE).
    Print the subprocess stderr to stderr if stderr=PIPE and there's
    any data.

    """
    assert 'stdout' not in kwargs
    kwargs['stdout'] = PIPE
    return ex(cmd, **kwargs)
