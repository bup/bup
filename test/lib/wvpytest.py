import pytest

def WVPASS(cond = True):
    assert cond

def WVFAIL(cond = True):
    assert not cond

def WVPASSEQ(a, b):
    assert a == b

def WVPASSNE(a, b):
    assert a != b

def WVPASSLT(a, b):
    assert a < b

def WVPASSLE(a, b):
    assert a <= b

def WVPASSGT(a, b):
    assert a > b

def WVPASSGE(a, b):
    assert a >= b

def WVEXCEPT(etype, func, *args, **kwargs):
    with pytest.raises(etype):
        func(*args, **kwargs)

def WVCHECK(cond, msg):
    assert cond, msg

def WVMSG(msg):
    print(msg)

wvpass = WVPASS
wvfail = WVFAIL
wvpasseq = WVPASSEQ
wvpassne = WVPASSNE
wvpaslt = WVPASSLT
wvpassle = WVPASSLE
wvpassgt = WVPASSGT
wvpassge = WVPASSGE
wvexcept = WVEXCEPT
wvcheck = WVCHECK
wvmsg = WVMSG
wvstart = WVMSG
