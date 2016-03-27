
from contextlib import contextmanager
from os.path import basename, dirname, realpath
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
            print '! %-70s %s' % ('%s:%-4d %s' % (basename(src_file),
                                                  src_line,
                                                  msg),
                                  'FAILED')
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
