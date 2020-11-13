
from __future__ import absolute_import
from os.path import basename, dirname, realpath
from time import tzset
from traceback import extract_stack
import os
import pytest
import subprocess
import sys

sys.path[:0] = ['lib']

from bup import helpers
from bup.compat import environ, fsencode


_bup_src_top = realpath(dirname(fsencode(__file__)))

# The "pwd -P" here may not be appropriate in the long run, but we
# need it until we settle the relevant drecurse/exclusion questions:
# https://groups.google.com/forum/#!topic/bup-list/9ke-Mbp10Q0
os.chdir(realpath(os.getcwd()))

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

@pytest.fixture(autouse=True)
def ephemeral_env_changes():
    orig_env = environ.copy()
    yield None
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
    os.chdir(_bup_src_top)

@pytest.fixture()
def tmpdir(tmp_path):
    try:
        yield bytes(tmp_path)
    finally:
        subprocess.call([b'chmod', b'-R', b'u+rwX', bytes(tmp_path)])
        # FIXME: delete only if there are no errors
        #subprocess.call(['rm', '-rf', tmpdir])
