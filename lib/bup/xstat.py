"""Enhanced stat operations for bup."""

from time import strftime
import os, sys, time
import stat as pystat


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


if not sys.platform.startswith('cygwin'):
    stat = os.stat
    fstat = os.fstat
    lstat = os.lstat
else:
    # These are potentially redundant until/unless we remove the
    # metadata _add_common guards (which we could, given that posix
    # allows negative values).
    def stat(path):
        st = os.stat(path)
        assert st.st_uid >= 0, st
        assert st.st_gid >= 0, st
        return st
    def fstat(path):
        st = os.fstat(path)
        assert st.st_uid >= 0, st
        assert st.st_gid >= 0, st
        return st
    def lstat(path):
        st = os.lstat(path)
        assert st.st_uid >= 0, st
        assert st.st_gid >= 0, st
        return st


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
