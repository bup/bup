#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

import sys, os, errno

from bup import options, git, vfs, xstat
from bup.helpers import buglvl, log
from pprint import pprint

try:
    import fuse
except ImportError:
    log('error: cannot find the python "fuse" module; please install it\n')
    sys.exit(1)


cache = {}
def cache_get(top, path):
    parts = path.split('/')
    cache[('',)] = top
    c = None
    max = len(parts)
    if buglvl >= 1:
        log('cache: %r\n' % cache.keys())
    for i in range(max):
        pre = parts[:max-i]
        if buglvl >= 1:
            log('cache trying: %r\n' % pre)
        c = cache.get(tuple(pre))
        if c:
            rest = parts[max-i:]
            for r in rest:
                if buglvl >= 1:
                    log('resolving %r from %r\n' % (r, c.fullname()))
                c = c.lresolve(r)
                key = tuple(pre + [r])
                if buglvl >= 1:
                    log('saving: %r\n' % (key,))
                cache[key] = c
            break
    assert(c)
    return c


class BupFs(fuse.Fuse):
    def __init__(self, top, meta=False, verbose=0):
        fuse.Fuse.__init__(self)
        self.top = top
        self.meta = meta
        self.verbose = verbose
    
    def getattr(self, path):
        if self.verbose > 0:
            log('--getattr(%r)\n' % path)
        try:
            node = cache_get(self.top, path)
            st = fuse.Stat(st_mode=node.mode,
                           st_nlink=node.nlinks(),
                           st_uid=os.getuid(),
                           st_gid=os.getgid(),
                           # Until/unless we store the size in m.
                           st_size=node.size())
            if self.meta:
                m = node.metadata()
                if m:
                    st.st_mode = m.mode
                    st.st_uid = m.uid
                    st.st_gid = m.gid
                    st.st_atime = max(0, xstat.fstime_floor_secs(m.atime))
                    st.st_mtime = max(0, xstat.fstime_floor_secs(m.mtime))
                    st.st_ctime = max(0, xstat.fstime_floor_secs(m.ctime))
            return st
        except vfs.NoSuchFile:
            return -errno.ENOENT

    def readdir(self, path, offset):
        if self.verbose > 0:
            log('--readdir(%r)\n' % path)
        node = cache_get(self.top, path)
        yield fuse.Direntry('.')
        yield fuse.Direntry('..')
        for sub in node.subs():
            yield fuse.Direntry(sub.name)

    def readlink(self, path):
        if self.verbose > 0:
            log('--readlink(%r)\n' % path)
        node = cache_get(self.top, path)
        return node.readlink()

    def open(self, path, flags):
        if self.verbose > 0:
            log('--open(%r)\n' % path)
        node = cache_get(self.top, path)
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & accmode) != os.O_RDONLY:
            return -errno.EACCES
        node.open()

    def release(self, path, flags):
        if self.verbose > 0:
            log('--release(%r)\n' % path)

    def read(self, path, size, offset):
        if self.verbose > 0:
            log('--read(%r)\n' % path)
        n = cache_get(self.top, path)
        o = n.open()
        o.seek(offset)
        return o.read(size)


if not hasattr(fuse, '__version__'):
    raise RuntimeError, "your fuse module is too old for fuse.__version__"
fuse.fuse_python_api = (0, 2)


optspec = """
bup fuse [-d] [-f] <mountpoint>
--
f,foreground  run in foreground
d,debug       run in the foreground and display FUSE debug information
o,allow-other allow other users to access the filesystem
meta          report original metadata for paths when available
v,verbose     increase log output (can be used more than once)
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) != 1:
    o.fatal("exactly one argument expected")

git.check_repo_or_die()
top = vfs.RefList(None)
f = BupFs(top, meta=opt.meta, verbose=opt.verbose)
f.fuse_args.mountpoint = extra[0]
if opt.debug:
    f.fuse_args.add('debug')
if opt.foreground:
    f.fuse_args.setmod('foreground')
print f.multithreaded
f.multithreaded = False
if opt.allow_other:
    f.fuse_args.add('allow_other')

f.main()
