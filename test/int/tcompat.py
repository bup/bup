
from __future__ import absolute_import, print_function

from wvtest import *

from bup.compat import pending_raise

@wvtest
def test_pending_raise():
    outer = Exception('outer')
    inner = Exception('inner')

    try:
        try:
            raise outer
        except Exception as ex:
            with pending_raise(ex):
                pass
    except Exception as ex:
        WVPASSEQ(outer, ex)
        WVPASSEQ(None, getattr(outer, '__context__', None))

    try:
        try:
            raise outer
        except Exception as ex:
            with pending_raise(ex):
                raise inner
    except Exception as ex:
        WVPASSEQ(inner, ex)
        WVPASSEQ(None, getattr(outer, '__context__', None))
        WVPASSEQ(outer, getattr(inner, '__context__', None))
