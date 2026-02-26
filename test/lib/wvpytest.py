
import pytest


def wvpass(cond = True, fail_value=None):
    if fail_value:
        assert cond, fail_value
    else:
        assert cond

def wvfail(cond = True):
    assert not cond

def wvpasseq(a, b, fail_value=None):
    if fail_value:
        assert a == b, fail_value
    else:
        assert a == b

def wvpassne(a, b):
    assert a != b

def wvpasslt(a, b):
    assert a < b

def wvpassle(a, b):
    assert a <= b

def wvpassgt(a, b):
    assert a > b

def wvpassge(a, b):
    assert a >= b

def wvexcept(etype, func, *args, **kwargs):
    with pytest.raises(etype):
        func(*args, **kwargs)

def wvcheck(cond, msg):
    assert cond, msg

def wvmsg(msg):
    print(msg)

wvstart = wvmsg


WVPASS = wvpass
WVFAIL = wvfail
WVPASSEQ = wvpasseq
WVPASSNE = wvpassne
WVPASSLT = wvpasslt
WVPASSLE = wvpassle
WVPASSGT = wvpassgt
WVPASSGE = wvpassge
WVEXCEPT = wvexcept
WVCHECK = wvcheck
WVMSG = wvmsg
WVSTART = wvmsg
