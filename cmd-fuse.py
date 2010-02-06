#!/usr/bin/env python
import sys, os, stat, errno, fuse, re, time, tempfile
import options, git
from helpers import *


def namesplit(path):
    l = path.split('/', 3)
    ref = None
    date = None
    dir = None
    assert(l[0] == '')
    if len(l) > 1:
        ref = l[1] or None
    if len(l) > 2:
        date = l[2]
    if len(l) > 3:
        dir = l[3]
    return (ref, date, dir)


# FIXME: iterating through a file just to check its size is super slow!
def sz(it):
    count = 0
    for d in it:
        count += len(d)
    return count


def date_to_commit(ref, datestr):
    dates = dates_for_ref(ref)
    dates.sort(reverse=True)
    try:
        dp = time.strptime(datestr, '%Y-%m-%d-%H%M%S')
    except ValueError:
        dp = time.strptime(datestr, '%Y-%m-%d')
    dt = time.mktime(dp)
    commit = None
    for (d,commit) in dates:
        if d <= dt: break
    assert(commit)
    return commit


refdates = {}
def dates_for_ref(ref):
    dates = refdates.get(ref)
    if not dates:
        dates = refdates[ref] = list(git.rev_list(ref))
        dates.sort()
    return dates


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


statcache = {}
filecache = {}


class BupFs(fuse.Fuse):
    def getattr(self, path):
        log('--getattr(%r)\n' % path)
        sc = statcache.get(path)
        if sc:
            return sc
        (ref,date,filename) = namesplit(path)
        if not ref:
            st = Stat()
            st.st_mode = stat.S_IFDIR | 0755
            st.st_nlink = 1  # FIXME
            statcache[path] = st
            return st
        elif not date or not filename:
            st = Stat()
            try:
                git.read_ref(ref)
            except git.GitError:
                pass
            st.st_mode = stat.S_IFDIR | 0755
            st.st_nlink = 1  # FIXME
            statcache[path] = st
            return st
        else:
            st = Stat()
            commit = date_to_commit(ref, date)
            (dir,name) = os.path.split(filename)
            it = cp.get('%s:%s' % (commit.encode('hex'), dir))
            type = it.next()
            if type == 'tree':
                for (mode,n,sha) in git._treeparse(''.join(it)):
                    if n == name:
                        st.st_mode = int(mode, 8)
                        st.st_nlink = 1  # FIXME
                        if stat.S_ISDIR(st.st_mode):
                            st.st_size = 1024
                        else:
                            fileid = '%s:%s' % (commit.encode('hex'), filename)
                            st.st_size = sz(cp.join(fileid))
                        statcache[path] = st
                        return st
        return -errno.ENOENT

    def readdir(self, path, offset):
        log('--readdir(%r)\n' % path)
        yield fuse.Direntry('.')
        yield fuse.Direntry('..')
        (ref,date,dir) = namesplit(path)
        if not ref:
            for (name,sha) in git.list_refs():
                name = re.sub('^refs/heads/', '', name)
                yield fuse.Direntry(name)
        elif not date:
            dates = dates_for_ref(ref)
            for (date,commit) in dates:
                l = time.localtime(date)
                yield fuse.Direntry(time.strftime('%Y-%m-%d-%H%M%S', l))
        else:
            commit = date_to_commit(ref, date)
            it = cp.get('%s:%s' % (commit.encode('hex'), dir or ''))
            type = it.next()
            if type == 'tree':
                for (mode,n,sha) in git._treeparse(''.join(it)):
                    yield fuse.Direntry(n)

    def readlink(self, path):
        log('--readlink(%r)\n' % path)
        self.open(path, os.O_RDONLY)  # FIXME: never released
        return self.read(path, 10000, 0)

    def open(self, path, flags):
        log('--open(%r)\n' % path)
        (ref,date,dir) = namesplit(path)
        if not dir:
            return -errno.ENOENT
        commit = date_to_commit(ref, date)
        try:
            it = cp.get('%s:%s' % (commit.encode('hex'), dir or ''))
        except KeyError:
            return -errno.ENOENT
        type = it.next()
        if type != 'blob':
            return -errno.EINVAL
        accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
        if (flags & accmode) != os.O_RDONLY:
            return -errno.EACCES

        f = tempfile.TemporaryFile()
        for blob in it:
            f.write(blob)
        f.flush()
        filecache[path] = f

    def release(self, path, flags):
        log('--release(%r)\n' % path)
        del filecache[path]

    def read(self, path, size, offset):
        log('--read(%r)\n' % path)
        f = filecache.get(path)
        if not f:
            return -errno.ENOENT
        f.seek(offset)
        return f.read(size)


if not hasattr(fuse, '__version__'):
    raise RuntimeError, "your fuse module is too old for fuse.__version__"
fuse.fuse_python_api = (0, 2)

optspec = """
bup fuse [-d] [-f] <mountpoint>
--
d,debug   increase debug level
f,foreground  run in foreground
"""
o = options.Options('bup fuse', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) != 1:
    log("bup fuse: exactly one argument expected\n")
    o.usage()

f = BupFs()
f.fuse_args.mountpoint = extra[0]
if opt.debug:
    f.fuse_args.add('debug')
if opt.foreground:
    f.fuse_args.setmod('foreground')
f.fuse_args.add('allow_other')

git.check_repo_or_die()
cp = git.CatPipe()
f.main()
