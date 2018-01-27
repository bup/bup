
from __future__ import absolute_import, print_function
from collections import namedtuple
from contextlib import contextmanager
from os.path import basename, dirname, realpath
from pipes import quote
from subprocess import PIPE, Popen, check_call
from traceback import extract_stack
import subprocess, sys, tempfile

from wvtest import WVPASSEQ, wvfailure_count

from bup import helpers


@contextmanager
def no_lingering_errors():
    def fail_if_errors():
        if helpers.saved_errors:
            bt = extract_stack()
            src_file, src_line, src_func, src_txt = bt[-4]
            msg = 'saved_errors ' + repr(helpers.saved_errors)
            print('! %-70s %s' % ('%s:%-4d %s' % (basename(src_file),
                                                  src_line,
                                                  msg),
                                  'FAILED'))
            sys.stdout.flush()
    fail_if_errors()
    helpers.clear_errors()
    yield
    fail_if_errors()
    helpers.clear_errors()


# Assumes (of course) this file is at the top-level of the source tree
_bup_tmp = realpath(dirname(__file__) + '/t/tmp')
helpers.mkdirp(_bup_tmp)


@contextmanager
def test_tempdir(prefix):
    initial_failures = wvfailure_count()
    tmpdir = tempfile.mkdtemp(dir=_bup_tmp, prefix=prefix)
    yield tmpdir
    if wvfailure_count() == initial_failures:
        subprocess.call(['chmod', '-R', 'u+rwX', tmpdir])
        subprocess.call(['rm', '-rf', tmpdir])


def logcmd(cmd):
    if isinstance(cmd, basestring):
        print(cmd, file=sys.stderr)
    else:
        print(' '.join(map(quote, cmd)), file=sys.stderr)


SubprocInfo = namedtuple('SubprocInfo', ('out', 'err', 'rc', 'p'))

def exo(cmd, input=None, stdin=None, stdout=PIPE, stderr=PIPE,
        shell=False, check=True):
    """Print cmd to stderr, run it, and return the resulting SubprocInfo.
    The keyword arguments are passed to Popen, and the defaults
    capture both stdout and stderr.

    """
    logcmd(cmd)
    p = Popen(cmd,
              stdin=(PIPE if input else stdin),
              stdout=stdout,
              stderr=stderr,
              shell=shell)
    out, err = p.communicate(input=input)
    if check and p.returncode != 0:
        raise Exception('subprocess %r failed with status %d%s'
                        % (' '.join(map(quote, cmd)),
                           p.returncode,
                           (', stderr: %r' % err) if stderr else ''))
    return SubprocInfo(out=out, err=err, rc=p.returncode, p=p)

def exc(cmd, input=None, stdout=None, stderr=None, shell=False, check=True):
    """Print cmd to stderr, run it, and return the resulting SubprocInfo.
    The keyword arguments are passed to Popen, and the defaults
    allow stdout and stderr to pass through.

    """
    return exo(cmd, input=input, stdout=stdout, stderr=stderr, shell=shell,
               check=check)
