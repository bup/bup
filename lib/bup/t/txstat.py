import math
from wvtest import *
import bup._helpers as _helpers
from bup.xstat import FSTime

def _test_fstime():
    def approx_eq(x, y):
        return math.fabs(x - y) < 1 / 10e8
    def ts_eq_ish(x, y):
        return approx_eq(x[0], y[0]) and approx_eq(x[1], y[1])
    def fst_eq_ish(x, y):
        return approx_eq(x.approx_secs(), y.approx_secs())
    def s_ns_eq_ish(fst, s, ns):
        (fst_s, fst_ns) = fst.secs_nsecs()
        return approx_eq(fst_s, s) and approx_eq(fst_ns, ns)
    from_secs = FSTime.from_secs
    from_ts = FSTime.from_timespec
    WVPASS(from_secs(0) == from_secs(0))
    WVPASS(from_secs(0) < from_secs(1))
    WVPASS(from_secs(-1) < from_secs(1))
    WVPASS(from_secs(1) > from_secs(0))
    WVPASS(from_secs(1) > from_secs(-1))

    WVPASS(fst_eq_ish(from_secs(0), from_ts((0, 0))))
    WVPASS(fst_eq_ish(from_secs(1), from_ts((1, 0))))
    WVPASS(fst_eq_ish(from_secs(-1), from_ts((-1, 0))))
    WVPASS(fst_eq_ish(from_secs(-0.5), from_ts((-1, 10**9 / 2))))
    WVPASS(fst_eq_ish(from_secs(-1.5), from_ts((-2, 10**9 / 2))))
    WVPASS(fst_eq_ish(from_secs(1 / 10e8), from_ts((0, 1))))
    WVPASS(fst_eq_ish(from_secs(-1 / 10e8), from_ts((-1, 10**9 - 1))))

    WVPASS(ts_eq_ish(from_secs(0).to_timespec(), (0, 0)))
    WVPASS(ts_eq_ish(from_secs(1).to_timespec(), (1, 0)))
    WVPASS(ts_eq_ish(from_secs(-1).to_timespec(), (-1, 0)))
    WVPASS(ts_eq_ish(from_secs(-0.5).to_timespec(), (-1, 10**9 / 2)))
    WVPASS(ts_eq_ish(from_secs(-1.5).to_timespec(), (-2, 10**9 / 2)))
    WVPASS(ts_eq_ish(from_secs(1 / 10e8).to_timespec(), (0, 1)))
    WVPASS(ts_eq_ish(from_secs(-1 / 10e8).to_timespec(), (-1, 10**9 - 1)))

    WVPASS(s_ns_eq_ish(from_secs(0), 0, 0))
    WVPASS(s_ns_eq_ish(from_secs(1), 1, 0))
    WVPASS(s_ns_eq_ish(from_secs(-1), -1, 0))
    WVPASS(s_ns_eq_ish(from_secs(-0.5), 0, - 10**9 / 2))
    WVPASS(s_ns_eq_ish(from_secs(-1.5), -1, - 10**9 / 2))
    WVPASS(s_ns_eq_ish(from_secs(-1 / 10e8), 0, -1))

@wvtest
def test_fstime():
    _test_fstime();
    if _helpers._have_ns_fs_timestamps: # Test native python timestamp rep too.
        orig = _helpers._have_ns_fs_timestamps
        try:
            _helpers._have_ns_fs_timestamps = None
            _test_fstime();
        finally:
            _helpers._have_ns_fs_timestamps = orig
