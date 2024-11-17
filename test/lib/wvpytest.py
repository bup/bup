import os
import pytest

# Precaution -- here just because it's already imported "everywhere".

os.environb[b'BUP_DIR'] = b'/dev/null'
os.environb[b'GIT_DIR'] = b'/dev/null'

def WVPASS(cond = True, fail_value=None):
    if fail_value:
        assert cond, fail_value
    else:
        assert cond

def WVFAIL(cond = True):
    assert not cond

def WVPASSEQ(a, b, fail_value=None):
    if fail_value:
        assert a == b, fail_value
    else:
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
