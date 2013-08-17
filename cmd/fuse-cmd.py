#!/usr/bin/env python
import sys, os, errno
from bup import options, git, vfs
from bup.helpers import *
try:
    import fuse
except ImportError:
    log('error: cannot find the python "fuse" module; please install it\n')
    sys.exit(1)


class Stat(fuse.Stat):
    def __init__(self):
        self.st_mode = 0
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 0
        self.st_uid = 0
        self.st_gid = 0
        self.st_size = 0
        self.st_atime = 0
        self.st_mtime = 0
        self.st_ctime = 0
        self.st_blocks = 0
        self.st_blksize = 0
        self.st_rdev = 0


cache = {}
def cache_get(top, path):
    parts = path.split('/')
    cache[('',)] = top
    c = None
    max = len(parts)
    #log('cache: %r\n' % cache.keys())
    for i in range(max):
        pre = parts[:max-i]
        #log('cache trying: %r\n' % pre)
        c = cache.get(tuple(pre))
        if c:
            rest = parts[max-i:]
            for r in rest:
                #log('resolving %r from %r\n' % (r, c.fullname()))
                c = c.lresolve(r)
                key = tuple(pre + [r])
                #log('saving: %r\n' % (key,))
                cache[key] = c
            break
    assert(c)
    return c
        
    

class BupFs(fuse.Fuse):
    def __init__(self, top):
        fuse.Fuse.__init__(self)
        self.top = top
    
    def getattr(self, path):
        log('--getattr(%r)\n' % path)
        try:
            node = cache_get(self.top, path)
            st = Stat()
            st.st_mode = node.mode
            st.st_nlink = node.nlinks()
            st.st_size = node.size()
            st.st_mtime = node.mtime
            st.st_ctime = node.ctime
            st.st_atime = node.atime
            return st
        except vfs.NoSuchFile:
            return -errno.ENOENT

    def readdir(self, path, offset):
        log('--readdir(%r)\n' % path)
        node = cache_get(self.top, path)
        yield fuse.Direntry('.')
        yield fuse.Direntry('..')
        for sub in node.subs():
            yield fuse.Direntry(sub.name)

    def readlink(self, path):
        log('--readlink(%r)\n' % path)
        node = cache_get(self.top, path)
        return node.readlink()

    def open(self, path, flags):
        log('--open(%r)\n' % path)
        node = cache_get(self.top, path)
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & accmode) != os.O_RDONLY:
            return -errno.EACCES
        node.open()

    def release(self, path, flags):
        log('--release(%r)\n' % path)

    def read(self, path, size, offset):
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
d,debug   increase debug level
f,foreground  run in foreground
o,allow-other allow other users to access the filesystem
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) != 1:
    o.fatal("exactly one argument expected")

git.check_repo_or_die()
top = vfs.RefList(None)
f = BupFs(top)
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
