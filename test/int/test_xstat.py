

from wvpytest import *

from bup import xstat


def test_fstime():
    WVPASSEQ(xstat.timespec_to_nsecs((0, 0)), 0)
    WVPASSEQ(xstat.timespec_to_nsecs((1, 0)), 10**9)
    WVPASSEQ(xstat.timespec_to_nsecs((0, 10**9 / 2)), 500000000)
    WVPASSEQ(xstat.timespec_to_nsecs((1, 10**9 / 2)), 1500000000)
    WVPASSEQ(xstat.timespec_to_nsecs((-1, 0)), -10**9)
    WVPASSEQ(xstat.timespec_to_nsecs((-1, 10**9 / 2)), -500000000)
    WVPASSEQ(xstat.timespec_to_nsecs((-2, 10**9 / 2)), -1500000000)
    WVPASSEQ(xstat.timespec_to_nsecs((0, -1)), -1)
    WVPASSEQ(type(xstat.timespec_to_nsecs((2, 22222222))), type(0))
    WVPASSEQ(type(xstat.timespec_to_nsecs((-2, 22222222))), type(0))

    WVPASSEQ(xstat.nsecs_to_timespec(0), (0, 0))
    WVPASSEQ(xstat.nsecs_to_timespec(10**9), (1, 0))
    WVPASSEQ(xstat.nsecs_to_timespec(500000000), (0, 10**9 / 2))
    WVPASSEQ(xstat.nsecs_to_timespec(1500000000), (1, 10**9 / 2))
    WVPASSEQ(xstat.nsecs_to_timespec(-10**9), (-1, 0))
    WVPASSEQ(xstat.nsecs_to_timespec(-500000000), (-1, 10**9 / 2))
    WVPASSEQ(xstat.nsecs_to_timespec(-1500000000), (-2, 10**9 / 2))
    x = xstat.nsecs_to_timespec(1977777778)
    WVPASSEQ(type(x[0]), type(0))
    WVPASSEQ(type(x[1]), type(0))
    x = xstat.nsecs_to_timespec(-1977777778)
    WVPASSEQ(type(x[0]), type(0))
    WVPASSEQ(type(x[1]), type(0))

    WVPASSEQ(xstat.nsecs_to_timeval(0), (0, 0))
    WVPASSEQ(xstat.nsecs_to_timeval(10**9), (1, 0))
    WVPASSEQ(xstat.nsecs_to_timeval(500000000), (0, (10**9 / 2) / 1000))
    WVPASSEQ(xstat.nsecs_to_timeval(1500000000), (1, (10**9 / 2) / 1000))
    WVPASSEQ(xstat.nsecs_to_timeval(-10**9), (-1, 0))
    WVPASSEQ(xstat.nsecs_to_timeval(-500000000), (-1, (10**9 / 2) / 1000))
    WVPASSEQ(xstat.nsecs_to_timeval(-1500000000), (-2, (10**9 / 2) / 1000))
    x = xstat.nsecs_to_timeval(1977777778)
    WVPASSEQ(type(x[0]), type(0))
    WVPASSEQ(type(x[1]), type(0))
    x = xstat.nsecs_to_timeval(-1977777778)
    WVPASSEQ(type(x[0]), type(0))
    WVPASSEQ(type(x[1]), type(0))

    WVPASSEQ(xstat.fstime_floor_secs(0), 0)
    WVPASSEQ(xstat.fstime_floor_secs(10**9 / 2), 0)
    WVPASSEQ(xstat.fstime_floor_secs(10**9), 1)
    WVPASSEQ(xstat.fstime_floor_secs(-10**9 / 2), -1)
    WVPASSEQ(xstat.fstime_floor_secs(-10**9), -1)
    WVPASSEQ(type(xstat.fstime_floor_secs(10**9 / 2)), type(0))
    WVPASSEQ(type(xstat.fstime_floor_secs(-10**9 / 2)), type(0))
