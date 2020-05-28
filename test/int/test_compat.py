
from __future__ import absolute_import, print_function

from bup.compat import pending_raise
from wvpytest import wvpasseq

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
        wvpasseq(outer, ex)
        wvpasseq(None, getattr(outer, '__context__', None))

    try:
        try:
            raise outer
        except Exception as ex:
            with pending_raise(ex):
                raise inner
    except Exception as ex:
        wvpasseq(inner, ex)
        wvpasseq(None, getattr(outer, '__context__', None))
        wvpasseq(outer, getattr(inner, '__context__', None))
