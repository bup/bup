
from __future__ import absolute_import, print_function
import errno, os, sys

try:
    import fuse
except ImportError:
    print('error: cannot find the python "fuse" module; please install it',
          file=sys.stderr)
    sys.exit(2)
if not hasattr(fuse, '__version__'):
    print('error: fuse module is too old for fuse.__version__', file=sys.stderr)
    sys.exit(2)
fuse.fuse_python_api = (0, 2)

if sys.version_info[0] > 2:
    try:
        fuse_ver = fuse.__version__.split('.')
        fuse_ver_maj = int(fuse_ver[0])
    except:
        log('error: cannot determine the fuse major version; please report',
            file=sys.stderr)
        sys.exit(2)
    if len(fuse_ver) < 3 or fuse_ver_maj < 1:
        print("error: fuse module can't handle binary data; please upgrade to 1.0+\n",
              file=sys.stderr)
        sys.exit(2)

from bup import options, git, vfs, xstat
from bup.compat import argv_bytes, fsdecode, py_maj
from bup.helpers import log
from bup.repo import LocalRepo


# FIXME: self.meta and want_meta?

# The path handling is just wrong, but the current fuse module can't
# handle bytes paths.

class BupFs(fuse.Fuse):
    def __init__(self, repo, verbose=0, fake_metadata=False):
        fuse.Fuse.__init__(self)
        self.repo = repo
        self.verbose = verbose
        self.fake_metadata = fake_metadata
    
    def getattr(self, path):
        path = argv_bytes(path)
        if self.verbose > 0:
            log('--getattr(%r)\n' % path)
        res = vfs.resolve(self.repo, path, want_meta=(not self.fake_metadata),
                          follow=False)
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
        st.st_uid = meta.uid or 0
        st.st_gid = meta.gid or 0
        st.st_atime = max(0, xstat.fstime_floor_secs(meta.atime))
        st.st_mtime = max(0, xstat.fstime_floor_secs(meta.mtime))
        st.st_ctime = max(0, xstat.fstime_floor_secs(meta.ctime))
        return st

    def readdir(self, path, offset):
        path = argv_bytes(path)
        assert not offset  # We don't return offsets, so offset should be unused
        res = vfs.resolve(self.repo, path, follow=False)
        dir_name, dir_item = res[-1]
        if not dir_item:
            yield -errno.ENOENT
        yield fuse.Direntry('..')
        # FIXME: make sure want_meta=False is being completely respected
        for ent_name, ent_item in vfs.contents(self.repo, dir_item, want_meta=False):
            fusename = fsdecode(ent_name.replace(b'/', b'-'))
            yield fuse.Direntry(fusename)

    def readlink(self, path):
        path = argv_bytes(path)
        if self.verbose > 0:
            log('--readlink(%r)\n' % path)
        res = vfs.resolve(self.repo, path, follow=False)
        name, item = res[-1]
        if not item:
            return -errno.ENOENT
        return fsdecode(vfs.readlink(self.repo, item))

    def open(self, path, flags):
        path = argv_bytes(path)
        if self.verbose > 0:
            log('--open(%r)\n' % path)
        res = vfs.resolve(self.repo, path, follow=False)
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
        path = argv_bytes(path)
        if self.verbose > 0:
            log('--read(%r)\n' % path)
        res = vfs.resolve(self.repo, path, follow=False)
        name, item = res[-1]
        if not item:
            return -errno.ENOENT
        with vfs.fopen(self.repo, item) as f:
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

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    if not opt.verbose:
        opt.verbose = 0

    # Set stderr to be line buffered, even if it's not connected to the console
    # so that we'll be able to see diagnostics in a timely fashion.
    errfd = sys.stderr.fileno()
    sys.stderr.flush()
    sys.stderr = os.fdopen(errfd, 'w', 1)

    if len(extra) != 1:
        o.fatal('only one mount point argument expected')

    git.check_repo_or_die()
    repo = LocalRepo()
    f = BupFs(repo=repo, verbose=opt.verbose, fake_metadata=(not opt.meta))

    # This is likely wrong, but the fuse module doesn't currently accept bytes
    f.fuse_args.mountpoint = extra[0]

    if opt.debug:
        f.fuse_args.add('debug')
    if opt.foreground:
        f.fuse_args.setmod('foreground')
    f.multithreaded = False
    if opt.allow_other:
        f.fuse_args.add('allow_other')
    f.main()
