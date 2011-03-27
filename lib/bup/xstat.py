"""Enhanced stat operations for bup."""
import os
from bup import _helpers


try:
    _have_utimensat = _helpers.utimensat
except AttributeError, e:
    _have_utimensat = False


def timespec_to_nsecs((ts_s, ts_ns)):
    # c.f. _helpers.c: timespec_vals_to_py_ns()
    if ts_ns < 0 or ts_ns > 999999999:
        raise Exception('invalid timespec nsec value')
    return ts_s * 10**9 + ts_ns


def nsecs_to_timespec(ns):
    """Return (s, ns) where ns is always non-negative
    and t = s + ns / 10e8""" # metadata record rep (and libc rep)
    ns = int(ns)
    return (ns / 10**9, ns % 10**9)


def fstime_floor_secs(ns):
    """Return largest integer not greater than ns / 10e8."""
    return int(ns) / 10**9;


def fstime_to_timespec(ns):
    return nsecs_to_timespec(ns)


if _have_utimensat:
    def lutime(path, times):
        atime = nsecs_to_timespec(times[0])
        mtime = nsecs_to_timespec(times[1])
        _helpers.utimensat(_helpers.AT_FDCWD, path, (atime, mtime),
                           _helpers.AT_SYMLINK_NOFOLLOW)
    def utime(path, times):
        atime = nsecs_to_timespec(times[0])
        mtime = nsecs_to_timespec(times[1])
        _helpers.utimensat(_helpers.AT_FDCWD, path, (atime, mtime), 0)
else:
    def lutime(path, times):
        return None

    def utime(path, times):
        atime = fstime_floor_secs(times[0])
        mtime = fstime_floor_secs(times[1])
        os.utime(path, (atime, mtime))


class stat_result:
    @staticmethod
    def from_xstat_rep(st):
        result = stat_result()
        (result.st_mode,
         result.st_ino,
         result.st_dev,
         result.st_nlink,
         result.st_uid,
         result.st_gid,
         result.st_rdev,
         result.st_size,
         result.st_atime,
         result.st_mtime,
         result.st_ctime) = st
        result.st_atime = timespec_to_nsecs(result.st_atime)
        result.st_mtime = timespec_to_nsecs(result.st_mtime)
        result.st_ctime = timespec_to_nsecs(result.st_ctime)
        return result


def stat(path):
    return stat_result.from_xstat_rep(_helpers.stat(path))


def fstat(path):
    return stat_result.from_xstat_rep(_helpers.fstat(path))


def lstat(path):
    return stat_result.from_xstat_rep(_helpers.lstat(path))
