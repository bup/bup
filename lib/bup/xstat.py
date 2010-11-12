"""Enhanced stat operations for bup."""
import os
import bup._helpers as _helpers


try:
    _have_utimensat = _helpers.utimensat
except AttributeError, e:
    _have_utimensat = False


class FSTime():
    # Class to represent filesystem timestamps.  Use integer
    # nanoseconds on platforms where we have the higher resolution
    # lstat.  Use the native python stat representation (floating
    # point seconds) otherwise.

    def __cmp__(self, x):
        return self._value.__cmp__(x._value)

    def to_timespec(self):
        """Return (s, ns) where ns is always non-negative
        and t = s + ns / 10e8""" # metadata record rep (and libc rep)
        s_ns = self.secs_nsecs()
        if s_ns[0] > 0 or s_ns[1] >= 0:
            return s_ns
        return (s_ns[0] - 1, 10**9 + s_ns[1]) # ns is negative

    if _helpers._have_ns_fs_timestamps: # Use integer nanoseconds.

        @staticmethod
        def from_secs(secs):
            ts = FSTime()
            ts._value = int(secs * 10**9)
            return ts

        @staticmethod
        def from_timespec(timespec):
            ts = FSTime()
            ts._value = timespec[0] * 10**9 + timespec[1]
            return ts

        @staticmethod
        def from_stat_time(stat_time):
            return FSTime.from_timespec(stat_time)

        def approx_secs(self):
            return self._value / 10e8;

        def secs_nsecs(self):
            "Return a (s, ns) pair: -1.5s -> (-1, -10**9 / 2)."
            if self._value >= 0:
                return (self._value / 10**9, self._value % 10**9)
            abs_val = -self._value
            return (- (abs_val / 10**9), - (abs_val % 10**9))

    else: # Use python default floating-point seconds.

        @staticmethod
        def from_secs(secs):
            ts = FSTime()
            ts._value = secs
            return ts

        @staticmethod
        def from_timespec(timespec):
            ts = FSTime()
            ts._value = timespec[0] + (timespec[1] / 10e8)
            return ts

        @staticmethod
        def from_stat_time(stat_time):
            ts = FSTime()
            ts._value = stat_time
            return ts

        def approx_secs(self):
            return self._value

        def secs_nsecs(self):
            "Return a (s, ns) pair: -1.5s -> (-1, -5**9)."
            x = math.modf(self._value)
            return (x[1], x[0] * 10**9)


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


class stat_result():

    @staticmethod
    def from_stat_rep(st):
        result = stat_result()
        if _helpers._have_ns_fs_timestamps:
            (result.st_mode,
             result.st_ino,
             result.st_dev,
             result.st_nlink,
             result.st_uid,
             result.st_gid,
             result.st_rdev,
             result.st_size,
             atime,
             mtime,
             ctime) = st
        else:
            result.st_mode = st.st_mode
            result.st_ino = st.st_ino
            result.st_dev = st.st_dev
            result.st_nlink = st.st_nlink
            result.st_uid = st.st_uid
            result.st_gid = st.st_gid
            result.st_rdev = st.st_rdev
            result.st_size = st.st_size
            atime = FSTime.from_stat_time(st.st_atime)
            mtime = FSTime.from_stat_time(st.st_mtime)
            ctime = FSTime.from_stat_time(st.st_ctime)
        result.st_atime = FSTime.from_stat_time(atime)
        result.st_mtime = FSTime.from_stat_time(mtime)
        result.st_ctime = FSTime.from_stat_time(ctime)
        return result


try:
    _stat = _helpers.stat
except AttributeError, e:
    _stat = os.stat

def stat(path):
    return stat_result.from_stat_rep(_stat(path))


try:
    _fstat = _helpers.fstat
except AttributeError, e:
    _fstat = os.fstat

def fstat(path):
    return stat_result.from_stat_rep(_fstat(path))


try:
    _lstat = _helpers.lstat
except AttributeError, e:
    _lstat = os.lstat

def lstat(path):
    return stat_result.from_stat_rep(_lstat(path))
