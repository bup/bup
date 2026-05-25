"""Enhanced stat operations for bup."""

from time import strftime
import os, time
import stat as pystat

from bup import _helpers
from bup._helpers import c_type_signed_size


def timespec_to_nsecs(ts):
    ts_s, ts_ns = ts
    return ts_s * 10**9 + ts_ns


def nsecs_to_timespec(ns):
    """Return (s, ns) where ns is always non-negative
    and t = s + ns / 10e8""" # metadata record rep
    ns = int(ns)
    return (ns // 10**9, ns % 10**9)


def nsecs_to_timeval(ns):
    """Return (s, us) where ns is always non-negative
    and t = s + us / 10e5"""
    ns = int(ns)
    return (ns // 10**9, (ns % 10**9) // 1000)


def fstime_floor_secs(ns):
    """Return largest integer not greater than ns / 10e8."""
    return int(ns) // 10**9


def fstime_to_timespec(ns):
    return nsecs_to_timespec(ns)


def fstime_to_sec_bytes(fstime):
    (s, ns) = fstime_to_timespec(fstime)
    if(s < 0):
        s += 1
    if ns == 0:
        return b'%d' % s
    return b'%d.%09d' % (s, ns)

def utime(path, times):
    """Times must be provided as (atime_ns, mtime_ns)."""
    os.utime(path, ns=times)
def lutime(path, times):
    """Times must be provided as (atime_ns, mtime_ns)."""
    os.utime(path, ns=times, follow_symlinks=False)


# We provide our own stat wrappers, and they produce an xstat_result,
# not an os.stat_result.  Our result provides a subset of the
# stat_result fields, and those fields respect the platform's actual
# types, in particular with respect to sign.  For example, dev_t is
# unsigned on Linux, and FreeBSD, but signed on macOS.
#
# Originally, Python treated dev_t as signed when populating
# os.stat_result regardless of the platform's actual definition (POSIX
# does not require it to be signed or unsigned), but Python eventually
# switched to treat dev_t as unsigned[1], no matter what the platform
# specified in <sys/types.h>, with the one exception that if the
# platform defines NODEV, then that can be returned, and is typically
# -1.  The switch to unsigned dev_t is/was also incomplete, for
# example still rejecting "high bit set" makedev values.
#
# Having our own stat functions ensures the vaules returned are
# consistent across platforms and across Python versions.  We also
# don't need or provide all of the stat fields right now.  For
# example, xstat_result only provides nanosecond timestamps via
# st_[amc]time_ns, not st_[amc]time.
#
# Note, though, that because we produce the platform's actual values
# for dev_t, etc., we have to be careful if we pass those values to
# Python functions, which is why we wrap mknod() below.
#
# [1] This is where Python switched to unsigned dev_t:
#
#   7111d9605f9db7aa0b095bb8ece7ccc0b8115c3f
#   gh-89928: Fix integer conversion of device numbers (GH-31794)
#   https://github.com/python/cpython/pull/31794
#
#   and it has been backported to various minor releases over time.

stat = _helpers.stat
lstat = _helpers.lstat
fstat = _helpers.stat

# Assuming two's complement, offset to convert negative values to
# their corresponding unsigned equivalents (as if coerced in C).
_dev_t_shift = 1 << abs(c_type_signed_size['dev_t']) * 8
_nodev = getattr(os, 'NODEV', 0)

def mknod(path, mode=0o600, device=0, *, dir_fd=None):
    # If needed, adapt our native dev_t values to the unsigned values
    # os.mknod expects.
    if device < 0 and device != _nodev:
        device += _dev_t_shift
    return os.mknod(path, mode, device, dir_fd=dir_fd)


def mode_str(mode):
    result = ''
    # FIXME: Other types?
    if pystat.S_ISREG(mode):
        result += '-'
    elif pystat.S_ISDIR(mode):
        result += 'd'
    elif pystat.S_ISCHR(mode):
        result += 'c'
    elif pystat.S_ISBLK(mode):
        result += 'b'
    elif pystat.S_ISFIFO(mode):
        result += 'p'
    elif pystat.S_ISLNK(mode):
        result += 'l'
    elif pystat.S_ISSOCK(mode):
        result += 's'
    else:
        result += '?'

    result += 'r' if (mode & pystat.S_IRUSR) else '-'
    result += 'w' if (mode & pystat.S_IWUSR) else '-'
    result += 'x' if (mode & pystat.S_IXUSR) else '-'
    result += 'r' if (mode & pystat.S_IRGRP) else '-'
    result += 'w' if (mode & pystat.S_IWGRP) else '-'
    result += 'x' if (mode & pystat.S_IXGRP) else '-'
    result += 'r' if (mode & pystat.S_IROTH) else '-'
    result += 'w' if (mode & pystat.S_IWOTH) else '-'
    result += 'x' if (mode & pystat.S_IXOTH) else '-'
    return result


def classification_str(mode, include_exec):
    if pystat.S_ISREG(mode):
        if include_exec \
           and (pystat.S_IMODE(mode) \
                & (pystat.S_IXUSR | pystat.S_IXGRP | pystat.S_IXOTH)):
            return '*'
        return ''
    if pystat.S_ISDIR(mode):
        return '/'
    if pystat.S_ISLNK(mode):
        return '@'
    if pystat.S_ISFIFO(mode):
        return '|'
    if pystat.S_ISSOCK(mode):
        return '='
    return ''


def local_time_str(t):
    if t is None:
        return None
    return strftime('%Y-%m-%d %H:%M', time.localtime(fstime_floor_secs(t)))
