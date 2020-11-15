
from __future__ import absolute_import
from os.path import dirname, realpath
from time import tzset
import os
import pytest
import sys

sys.path[:0] = ['lib']

from bup import helpers
from bup.compat import environ, fsencode


_bup_src_top = realpath(dirname(fsencode(__file__)))

# The "pwd -P" here may not be appropriate in the long run, but we
# need it until we settle the relevant drecurse/exclusion questions:
# https://groups.google.com/forum/#!topic/bup-list/9ke-Mbp10Q0
os.chdir(realpath(os.getcwd()))

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
