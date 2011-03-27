"""Enhanced stat operations for bup."""
import os
from bup import _helpers


try:
    _have_utimensat = _helpers.utimensat
except AttributeError, e:
    _have_utimensat = False


class FSTime:
    # Class to represent filesystem timestamps.  Use integer
    # nanoseconds on platforms where we have the higher resolution
    # lstat.  Use the native python stat representation (floating
    # point seconds) otherwise.

    def __cmp__(self, x):
        return self._value.__cmp__(x._value)
        
    def __repr__(self):
        return 'FSTime(%d)' % self._value
        
    def to_timespec(self):
        """Return (s, ns) where ns is always non-negative
        and t = s + ns / 10e8""" # metadata record rep (and libc rep)
        s_ns = self.secs_nsecs()
        if s_ns[0] > 0 or s_ns[1] >= 0:
            return s_ns
        return (s_ns[0] - 1, 10**9 + s_ns[1]) # ns is negative

    @staticmethod
    def from_secs(secs):
        ts = FSTime()
        ts._value = int(round(secs * 10**9))
        return ts

    @staticmethod
    def from_timespec(timespec):
        ts = FSTime()
        ts._value = timespec[0] * 10**9 + timespec[1]
        return ts

    def approx_secs(self):
        return self._value / 10e8;

    def secs_nsecs(self):
        "Return a (s, ns) pair: -1.5s -> (-1, -10**9 / 2)."
        if self._value >= 0:
            return (self._value / 10**9, self._value % 10**9)
        abs_val = -self._value
        return (- (abs_val / 10**9), - (abs_val % 10**9))


if _have_utimensat:
    def lutime(path, times):
        atime = times[0].to_timespec()
        mtime = times[1].to_timespec()
        return _helpers.utimensat(_helpers.AT_FDCWD, path, (atime, mtime),
                                  _helpers.AT_SYMLINK_NOFOLLOW)
    def utime(path, times):
        atime = times[0].to_timespec()
        mtime = times[1].to_timespec()
        return _helpers.utimensat(_helpers.AT_FDCWD, path, (atime, mtime), 0)
else:
    def lutime(path, times):
        return None

    def utime(path, times):
        atime = times[0].approx_secs()
        mtime = times[1].approx_secs()
        os.utime(path, (atime, mtime))


class stat_result:
    @staticmethod
    def from_stat_rep(st):
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
        result.st_atime = FSTime.from_timespec(result.st_atime)
        result.st_mtime = FSTime.from_timespec(result.st_mtime)
        result.st_ctime = FSTime.from_timespec(result.st_ctime)
        return result


def stat(path):
    return stat_result.from_stat_rep(_helpers.stat(path))


def fstat(path):
    return stat_result.from_stat_rep(_helpers.fstat(path))


def lstat(path):
    return stat_result.from_stat_rep(_helpers.lstat(path))
