#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import sys, os, errno

try:
    import fuse
except ImportError:
    log('error: cannot find the python "fuse" module; please install it\n')
    sys.exit(1)
if not hasattr(fuse, '__version__'):
    raise RuntimeError, "your fuse module is too old for fuse.__version__"
fuse.fuse_python_api = (0, 2)

from bup import options, git, vfs, xstat
from bup.helpers import log
from bup.repo import LocalRepo

# FIXME: self.meta and want_meta?

class BupFs(fuse.Fuse):
    def __init__(self, repo, verbose=0, fake_metadata=False):
        fuse.Fuse.__init__(self)
        self.repo = repo
        self.verbose = verbose
        self.fake_metadata = fake_metadata
    
    def getattr(self, path):
        global opt
        if self.verbose > 0:
            log('--getattr(%r)\n' % path)
        res = vfs.lresolve(self.repo, path, want_meta=(not self.fake_metadata))
        log('res: %r\n' % (res,))
        name, item = res[-1]
        if not item:
            return -errno.ENOENT
        if self.fake_metadata:
            item = vfs.augment_item_meta(self.repo, item, include_size=True)
        else:
            item = vfs.ensure_item_has_metadata(self.repo, item,
                                                include_size=True)
        meta = item.meta
        # FIXME: do we want/need to do anything more with nlink?
        st = fuse.Stat(st_mode=meta.mode, st_nlink=1, st_size=meta.size)
        st.st_mode = meta.mode
        st.st_uid = meta.uid
        st.st_gid = meta.gid
        st.st_atime = max(0, xstat.fstime_floor_secs(meta.atime))
        st.st_mtime = max(0, xstat.fstime_floor_secs(meta.mtime))
        st.st_ctime = max(0, xstat.fstime_floor_secs(meta.ctime))
        return st

    def readdir(self, path, offset):
        assert not offset  # We don't return offsets, so offset should be unused
        res = vfs.lresolve(self.repo, path)
        dir_name, dir_item = res[-1]
        if not dir_item:
            yield -errno.ENOENT
        yield fuse.Direntry('..')
        # FIXME: make sure want_meta=False is being completely respected
        for ent_name, ent_item in vfs.contents(repo, dir_item, want_meta=False):
            yield fuse.Direntry(ent_name.replace('/', '-'))

    def readlink(self, path):
        if self.verbose > 0:
            log('--readlink(%r)\n' % path)
        res = vfs.lresolve(self.repo, path)
        name, item = res[-1]
        if not item:
            return -errno.ENOENT
        return vfs.readlink(repo, item)

    def open(self, path, flags):
        if self.verbose > 0:
            log('--open(%r)\n' % path)
        res = vfs.lresolve(self.repo, path)
        name, item = res[-1]
        if not item:
            return -errno.ENOENT
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & accmode) != os.O_RDONLY:
            return -errno.EACCES
        # Return None since read doesn't need the file atm...
        # If we *do* return the file, it'll show up as the last argument
        #return vfs.fopen(repo, item)

    def read(self, path, size, offset):
        if self.verbose > 0:
            log('--read(%r)\n' % path)
        res = vfs.lresolve(self.repo, path)
        name, item = res[-1]
        if not item:
            return -errno.ENOENT
        with vfs.fopen(repo, item) as f:
            f.seek(offset)
            return f.read(size)

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
opt, flags, extra = o.parse(sys.argv[1:])

if len(extra) != 1:
    o.fatal('only one mount point argument expected')

git.check_repo_or_die()
repo = LocalRepo()
f = BupFs(repo=repo, verbose=opt.verbose, fake_metadata=(not opt.meta))
f.fuse_args.mountpoint = extra[0]
if opt.debug:
    f.fuse_args.add('debug')
if opt.foreground:
    f.fuse_args.setmod('foreground')
f.multithreaded = False
if opt.allow_other:
    f.fuse_args.add('allow_other')
f.main()
