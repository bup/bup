
from contextlib import ExitStack
from os.path import basename, dirname, realpath, relpath
from time import tzset
from shutil import rmtree
from sys import stderr
from tempfile import mkdtemp
from traceback import extract_stack
import errno
import os
import pytest
import re
import subprocess
import sys
import tempfile

sys.path[:0] = ['lib']

from bup import helpers
from bup.compat import environ, fsencode
from bup.helpers import finalized


_bup_src_top = realpath(dirname(fsencode(__file__)))

# The "pwd -P" here may not be appropriate in the long run, but we
# need it until we settle the relevant drecurse/exclusion questions:
# https://groups.google.com/forum/#!topic/bup-list/9ke-Mbp10Q0
os.chdir(realpath(os.getcwd()))

# Make the test results available to fixtures
@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    other_hooks = yield
    report = other_hooks.get_result()
    bup = item.__dict__.setdefault('bup', {})
    bup[report.when + '-report'] = report  # setup, call, teardown
    item.bup = bup

def bup_test_sort_order(item):
    # Pull some slower tests forward to speed parallel runs
    if item.fspath.basename in ('test_get.py', 'test-index.sh'):
        return (0, str(item.fspath))
    return (1, str(item.fspath))

def pytest_collection_modifyitems(session, config, items):
    items.sort(key=bup_test_sort_order)

@pytest.fixture(autouse=True)
def no_lingering_errors():
    def fail_if_errors():
        if helpers.saved_errors:
            bt = extract_stack()
            src_file, src_line, src_func, src_txt = bt[-4]
            msg = 'saved_errors ' + repr(helpers.saved_errors)
            assert False, '%s:%-4d %s' % (basename(src_file),
                                          src_line, msg)

    fail_if_errors()
    helpers.clear_errors()
    yield None
    fail_if_errors()
    helpers.clear_errors()

# Assumes (of course) this file is at the top-level of the source tree
_bup_test_dir = realpath(dirname(fsencode(__file__))) + b'/test'
_bup_tmp = _bup_test_dir + b'/tmp'
try:
    os.makedirs(_bup_tmp)
except OSError as e:
    if e.errno != errno.EEXIST:
        raise

@pytest.fixture(autouse=True)
def common_test_environment(request):
    orig_env = environ.copy()
    def restore_env(_):
        for k, orig_v in orig_env.items():
            v = environ.get(k)
            if v is not orig_v:
                environ[k] = orig_v
                if k == b'TZ':
                    tzset()
        for k in environ.keys():
            if k not in orig_env:
                del environ[k]
                if k == b'TZ':
                    tzset()
    rm_home = True
    def maybe_rm_home(home):
        if not rm_home:
            print('\nPreserving test HOME:', home, file=stderr)
            return
        rmtree(home)
    with finalized(mkdtemp(dir=_bup_tmp, prefix=b'home-'), maybe_rm_home) as home, \
         finalized(lambda _: os.chdir(_bup_src_top)), \
         finalized(restore_env):
        environ[b'HOME'] = home
        yield None
        if request.node.bup['call-report'].failed:
            rm_home = False

_safe_path_rx = re.compile(br'[^a-zA-Z0-9_-]')

@pytest.fixture()
def tmpdir(request):
    rp = realpath(fsencode(request.fspath))
    rp = relpath(rp, _bup_test_dir)
    if request.function:
        rp += b'-' + fsencode(request.function.__name__)
    safe = _safe_path_rx.sub(b'-', rp)
    tmpdir = tempfile.mkdtemp(dir=_bup_tmp, prefix=safe)
    yield tmpdir
    if request.node.bup['call-report'].failed:
        print('\nPreserving:', b'test/' + relpath(tmpdir, _bup_test_dir),
              file=sys.stderr)
    else:
        subprocess.call(['chmod', '-R', 'u+rwX', tmpdir])
        subprocess.call(['rm', '-rf', tmpdir])
