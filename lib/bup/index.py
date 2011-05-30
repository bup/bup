import os, stat, struct, tempfile
from bup import xstat
from bup.helpers import *

EMPTY_SHA = '\0'*20
FAKE_SHA = '\x01'*20
INDEX_HDR = 'BUPI\0\0\0\2'

# FIXME: guess I should have used 64-bit integers to store the mtime/ctime.
# NTFS mtime=0 corresponds to the year 1600, which can't be stored in a 32-bit
# time_t.  Next time we update the bupindex format, keep that in mind.
INDEX_SIG = '!IiiIIQII20sHII'

ENTLEN = struct.calcsize(INDEX_SIG)
FOOTER_SIG = '!Q'
FOOTLEN = struct.calcsize(FOOTER_SIG)

IX_EXISTS = 0x8000        # file exists on filesystem
IX_HASHVALID = 0x4000     # the stored sha1 matches the filesystem
IX_SHAMISSING = 0x2000    # the stored sha1 object doesn't seem to exist

class Error(Exception):
    pass


class Level:
    def __init__(self, ename, parent):
        self.parent = parent
        self.ename = ename
        self.list = []
        self.count = 0

    def write(self, f):
        (ofs,n) = (f.tell(), len(self.list))
        if self.list:
            count = len(self.list)
            #log('popping %r with %d entries\n' 
            #    % (''.join(self.ename), count))
            for e in self.list:
                e.write(f)
            if self.parent:
                self.parent.count += count + self.count
        return (ofs,n)


def _golevel(level, f, ename, newentry, tmax):
    # close nodes back up the tree
    assert(level)
    while ename[:len(level.ename)] != level.ename:
        n = BlankNewEntry(level.ename[-1], tmax)
        n.flags |= IX_EXISTS
        (n.children_ofs,n.children_n) = level.write(f)
        level.parent.list.append(n)
        level = level.parent

    # create nodes down the tree
    while len(level.ename) < len(ename):
        level = Level(ename[:len(level.ename)+1], level)

    # are we in precisely the right place?
    assert(ename == level.ename)
    n = newentry or BlankNewEntry(ename and level.ename[-1] or None, tmax)
    (n.children_ofs,n.children_n) = level.write(f)
    if level.parent:
        level.parent.list.append(n)
    level = level.parent

    return level


class Entry:
    def __init__(self, basename, name, tmax):
        self.basename = str(basename)
        self.name = str(name)
        self.tmax = tmax
        self.children_ofs = 0
        self.children_n = 0

    def __repr__(self):
        return ("(%s,0x%04x,%d,%d,%d,%d,%d,%s/%s,0x%04x,0x%08x/%d)" 
                % (self.name, self.dev,
                   self.ctime, self.mtime, self.uid, self.gid,
                   self.size, oct(self.mode), oct(self.gitmode),
                   self.flags, self.children_ofs, self.children_n))

    def packed(self):
        try:
            return struct.pack(INDEX_SIG,
                           self.dev, self.ctime, self.mtime, 
                           self.uid, self.gid, self.size, self.mode,
                           self.gitmode, self.sha, self.flags,
                           self.children_ofs, self.children_n)
        except (DeprecationWarning, struct.error), e:
            log('pack error: %s (%r)\n' % (e, self))
            raise

    def from_stat(self, st, tstart):
        old = (self.dev, self.ctime, self.mtime,
               self.uid, self.gid, self.size, self.flags & IX_EXISTS)
        new = (st.st_dev,
               xstat.fstime_floor_secs(st.st_ctime),
               xstat.fstime_floor_secs(st.st_mtime),
               st.st_uid, st.st_gid, st.st_size, IX_EXISTS)
        self.dev = st.st_dev
        self.ctime = xstat.fstime_floor_secs(st.st_ctime)
        self.mtime = xstat.fstime_floor_secs(st.st_mtime)
        self.uid = st.st_uid
        self.gid = st.st_gid
        self.size = st.st_size
        self.mode = st.st_mode
        self.flags |= IX_EXISTS
        if xstat.fstime_floor_secs(st.st_ctime) >= tstart or old != new \
              or self.sha == EMPTY_SHA or not self.gitmode:
            self.invalidate()
        self._fixup()
        
    def _fixup(self):
        if self.uid < 0:
            self.uid += 0x100000000
        if self.gid < 0:
            self.gid += 0x100000000
        assert(self.uid >= 0)
        assert(self.gid >= 0)
        self.mtime = self._fixup_time(self.mtime)
        self.ctime = self._fixup_time(self.ctime)

    def _fixup_time(self, t):
        if t < -0x80000000:  # can happen in NTFS on 64-bit linux
            return 0
        elif self.tmax != None and t > self.tmax:
            return self.tmax
        else:
            return t

    def is_valid(self):
        f = IX_HASHVALID|IX_EXISTS
        return (self.flags & f) == f

    def invalidate(self):
        self.flags &= ~IX_HASHVALID

    def validate(self, gitmode, sha):
        assert(sha)
        assert(gitmode)
        assert(gitmode+0 == gitmode)
        self.gitmode = gitmode
        self.sha = sha
        self.flags |= IX_HASHVALID|IX_EXISTS

    def exists(self):
        return not self.is_deleted()

    def sha_missing(self):
        return (self.flags & IX_SHAMISSING) or not (self.flags & IX_HASHVALID)

    def is_deleted(self):
        return (self.flags & IX_EXISTS) == 0

    def set_deleted(self):
        if self.flags & IX_EXISTS:
            self.flags &= ~(IX_EXISTS | IX_HASHVALID)

    def is_real(self):
        return not self.is_fake()

    def is_fake(self):
        return not self.ctime

    def __cmp__(a, b):
        return (cmp(b.name, a.name)
                or cmp(a.is_valid(), b.is_valid())
                or cmp(a.is_fake(), b.is_fake()))

    def write(self, f):
        f.write(self.basename + '\0' + self.packed())


class NewEntry(Entry):
    def __init__(self, basename, name, tmax, dev, ctime, mtime, uid, gid,
                 size, mode, gitmode, sha, flags, children_ofs, children_n):
        Entry.__init__(self, basename, name, tmax)
        (self.dev, self.ctime, self.mtime, self.uid, self.gid,
         self.size, self.mode, self.gitmode, self.sha,
         self.flags, self.children_ofs, self.children_n
         ) = (dev, int(ctime), int(mtime), uid, gid,
              size, mode, gitmode, sha, flags, children_ofs, children_n)
        self._fixup()


class BlankNewEntry(NewEntry):
    def __init__(self, basename, tmax):
        NewEntry.__init__(self, basename, basename, tmax,
                          0, 0, 0, 0, 0, 0, 0,
                          0, EMPTY_SHA, 0, 0, 0)


class ExistingEntry(Entry):
    def __init__(self, parent, basename, name, m, ofs):
        Entry.__init__(self, basename, name, None)
        self.parent = parent
        self._m = m
        self._ofs = ofs
        (self.dev, self.ctime, self.mtime, self.uid, self.gid,
         self.size, self.mode, self.gitmode, self.sha,
         self.flags, self.children_ofs, self.children_n
         ) = struct.unpack(INDEX_SIG, str(buffer(m, ofs, ENTLEN)))

    # effectively, we don't bother messing with IX_SHAMISSING if
    # not IX_HASHVALID, since it's redundant, and repacking is more
    # expensive than not repacking.
    # This is implemented by having sha_missing() check IX_HASHVALID too.
    def set_sha_missing(self, val):
        val = val and 1 or 0
        oldval = self.sha_missing() and 1 or 0
        if val != oldval:
            flag = val and IX_SHAMISSING or 0
            newflags = (self.flags & (~IX_SHAMISSING)) | flag
            self.flags = newflags
            self.repack()

    def unset_sha_missing(self, flag):
        if self.flags & IX_SHAMISSING:
            self.flags &= ~IX_SHAMISSING
            self.repack()

    def repack(self):
        self._m[self._ofs:self._ofs+ENTLEN] = self.packed()
        if self.parent and not self.is_valid():
            self.parent.invalidate()
            self.parent.repack()

    def iter(self, name=None, wantrecurse=None):
        dname = name
        if dname and not dname.endswith('/'):
            dname += '/'
        ofs = self.children_ofs
        assert(ofs <= len(self._m))
        assert(self.children_n < 1000000)
        for i in xrange(self.children_n):
            eon = self._m.find('\0', ofs)
            assert(eon >= 0)
            assert(eon >= ofs)
            assert(eon > ofs)
            basename = str(buffer(self._m, ofs, eon-ofs))
            child = ExistingEntry(self, basename, self.name + basename,
                                  self._m, eon+1)
            if (not dname
                 or child.name.startswith(dname)
                 or child.name.endswith('/') and dname.startswith(child.name)):
                if not wantrecurse or wantrecurse(child):
                    for e in child.iter(name=name, wantrecurse=wantrecurse):
                        yield e
            if not name or child.name == name or child.name.startswith(dname):
                yield child
            ofs = eon + 1 + ENTLEN

    def __iter__(self):
        return self.iter()
            

class Reader:
    def __init__(self, filename):
        self.filename = filename
        self.m = ''
        self.writable = False
        self.count = 0
        f = None
        try:
            f = open(filename, 'r+')
        except IOError, e:
            if e.errno == errno.ENOENT:
                pass
            else:
                raise
        if f:
            b = f.read(len(INDEX_HDR))
            if b != INDEX_HDR:
                log('warning: %s: header: expected %r, got %r'
                                 % (filename, INDEX_HDR, b))
            else:
                st = os.fstat(f.fileno())
                if st.st_size:
                    self.m = mmap_readwrite(f)
                    self.writable = True
                    self.count = struct.unpack(FOOTER_SIG,
                          str(buffer(self.m, st.st_size-FOOTLEN, FOOTLEN)))[0]

    def __del__(self):
        self.close()

    def __len__(self):
        return int(self.count)

    def forward_iter(self):
        ofs = len(INDEX_HDR)
        while ofs+ENTLEN <= len(self.m)-FOOTLEN:
            eon = self.m.find('\0', ofs)
            assert(eon >= 0)
            assert(eon >= ofs)
            assert(eon > ofs)
            basename = str(buffer(self.m, ofs, eon-ofs))
            yield ExistingEntry(None, basename, basename, self.m, eon+1)
            ofs = eon + 1 + ENTLEN

    def iter(self, name=None, wantrecurse=None):
        if len(self.m) > len(INDEX_HDR)+ENTLEN:
            dname = name
            if dname and not dname.endswith('/'):
                dname += '/'
            root = ExistingEntry(None, '/', '/',
                                 self.m, len(self.m)-FOOTLEN-ENTLEN)
            for sub in root.iter(name=name, wantrecurse=wantrecurse):
                yield sub
            if not dname or dname == root.name:
                yield root

    def __iter__(self):
        return self.iter()

    def exists(self):
        return self.m

    def save(self):
        if self.writable and self.m:
            self.m.flush()

    def close(self):
        self.save()
        if self.writable and self.m:
            self.m.close()
            self.m = None
            self.writable = False

    def filter(self, prefixes, wantrecurse=None):
        for (rp, path) in reduce_paths(prefixes):
            for e in self.iter(rp, wantrecurse=wantrecurse):
                assert(e.name.startswith(rp))
                name = path + e.name[len(rp):]
                yield (name, e)


# FIXME: this function isn't very generic, because it splits the filename
# in an odd way and depends on a terminating '/' to indicate directories.
def pathsplit(p):
    """Split a path into a list of elements of the file system hierarchy."""
    l = p.split('/')
    l = [i+'/' for i in l[:-1]] + l[-1:]
    if l[-1] == '':
        l.pop()  # extra blank caused by terminating '/'
    return l


class Writer:
    def __init__(self, filename, tmax):
        self.rootlevel = self.level = Level([], None)
        self.f = None
        self.count = 0
        self.lastfile = None
        self.filename = None
        self.filename = filename = realpath(filename)
        self.tmax = tmax
        (dir,name) = os.path.split(filename)
        (ffd,self.tmpname) = tempfile.mkstemp('.tmp', filename, dir)
        self.f = os.fdopen(ffd, 'wb', 65536)
        self.f.write(INDEX_HDR)

    def __del__(self):
        self.abort()

    def abort(self):
        f = self.f
        self.f = None
        if f:
            f.close()
            os.unlink(self.tmpname)

    def flush(self):
        if self.level:
            self.level = _golevel(self.level, self.f, [], None, self.tmax)
            self.count = self.rootlevel.count
            if self.count:
                self.count += 1
            self.f.write(struct.pack(FOOTER_SIG, self.count))
            self.f.flush()
        assert(self.level == None)

    def close(self):
        self.flush()
        f = self.f
        self.f = None
        if f:
            f.close()
            os.rename(self.tmpname, self.filename)

    def _add(self, ename, entry):
        if self.lastfile and self.lastfile <= ename:
            raise Error('%r must come before %r' 
                             % (''.join(e.name), ''.join(self.lastfile)))
            self.lastfile = e.name
        self.level = _golevel(self.level, self.f, ename, entry, self.tmax)

    def add(self, name, st, hashgen = None):
        endswith = name.endswith('/')
        ename = pathsplit(name)
        basename = ename[-1]
        #log('add: %r %r\n' % (basename, name))
        flags = IX_EXISTS
        sha = None
        if hashgen:
            (gitmode, sha) = hashgen(name)
            flags |= IX_HASHVALID
        else:
            (gitmode, sha) = (0, EMPTY_SHA)
        if st:
            isdir = stat.S_ISDIR(st.st_mode)
            assert(isdir == endswith)
            e = NewEntry(basename, name, self.tmax, st.st_dev,
                         xstat.fstime_floor_secs(st.st_ctime),
                         xstat.fstime_floor_secs(st.st_mtime),
                         st.st_uid, st.st_gid,
                         st.st_size, st.st_mode, gitmode, sha, flags,
                         0, 0)
        else:
            assert(endswith)
            e = BlankNewEntry(basename, tmax)
            e.gitmode = gitmode
            e.sha = sha
            e.flags = flags
        self._add(ename, e)

    def add_ixentry(self, e):
        e.children_ofs = e.children_n = 0
        self._add(pathsplit(e.name), e)

    def new_reader(self):
        self.flush()
        return Reader(self.tmpname)


def reduce_paths(paths):
    xpaths = []
    for p in paths:
        rp = realpath(p)
        try:
            st = os.lstat(rp)
            if stat.S_ISDIR(st.st_mode):
                rp = slashappend(rp)
                p = slashappend(p)
            xpaths.append((rp, p))
        except OSError, e:
            add_error('reduce_paths: %s' % e)
    xpaths.sort()

    paths = []
    prev = None
    for (rp, p) in xpaths:
        if prev and (prev == rp 
                     or (prev.endswith('/') and rp.startswith(prev))):
            continue # already superceded by previous path
        paths.append((rp, p))
        prev = rp
    paths.sort(reverse=True)
    return paths

def merge(*iters):
    def pfunc(count, total):
        qprogress('bup: merging indexes (%d/%d)\r' % (count, total))
    def pfinal(count, total):
        progress('bup: merging indexes (%d/%d), done.\n' % (count, total))
    return merge_iter(iters, 1024, pfunc, pfinal, key='name')
