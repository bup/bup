import os, stat, time, struct, tempfile
from helpers import *

EMPTY_SHA = '\0'*20
FAKE_SHA = '\x01'*20
INDEX_HDR = 'BUPI\0\0\0\2'
INDEX_SIG = '!IIIIIQII20sHII'
ENTLEN = struct.calcsize(INDEX_SIG)

IX_EXISTS = 0x8000
IX_HASHVALID = 0x4000

class Error(Exception):
    pass


def _encode(dev, ctime, mtime, uid, gi8d, size, mode, gitmode, sha, flags):
    return struct.pack(INDEX_SIG,
                       dev, ctime, mtime, uid, gid, size, mode,
                       gitmode, sha, flags)

class Entry:
    def __init__(self, name):
        self.name = str(name)
        self.children_ofs = 0
        self.children_n = 0

    def __repr__(self):
        return ("(%s,0x%04x,%d,%d,%d,%d,%d,0x%04x)" 
                % (self.name, self.dev,
                   self.ctime, self.mtime, self.uid, self.gid,
                   self.size, self.flags))

    def packed(self):
        return struct.pack(INDEX_SIG,
                           self.dev, self.ctime, self.mtime, 
                           self.uid, self.gid, self.size, self.mode,
                           self.gitmode, self.sha, self.flags,
                           self.children_ofs, self.children_n)

    def from_stat(self, st, tstart):
        old = (self.dev, self.ctime, self.mtime,
               self.uid, self.gid, self.size, self.flags & IX_EXISTS)
        new = (st.st_dev, int(st.st_ctime), int(st.st_mtime),
               st.st_uid, st.st_gid, st.st_size, IX_EXISTS)
        self.dev = st.st_dev
        self.ctime = int(st.st_ctime)
        self.mtime = int(st.st_mtime)
        self.uid = st.st_uid
        self.gid = st.st_gid
        self.size = st.st_size
        self.mode = st.st_mode
        self.flags |= IX_EXISTS
        if int(st.st_ctime) >= tstart or old != new:
            self.flags &= ~IX_HASHVALID
            self.set_dirty()

    def validate(self, sha):
        assert(sha)
        self.sha = sha
        self.flags |= IX_HASHVALID

    def set_deleted(self):
        self.flags &= ~(IX_EXISTS | IX_HASHVALID)
        self.set_dirty()

    def set_dirty(self):
        pass # FIXME

    def __cmp__(a, b):
        return cmp(a.name, b.name)


class NewEntry(Entry):
    def __init__(self, name, dev, ctime, mtime, uid, gid,
                 size, mode, gitmode, sha, flags, children_ofs, children_n):
        Entry.__init__(self, name)
        (self.dev, self.ctime, self.mtime, self.uid, self.gid,
         self.size, self.mode, self.gitmode, self.sha,
         self.flags, self.children_ofs, self.children_n
         ) = (dev, int(ctime), int(mtime), uid, gid,
              size, mode, gitmode, sha, flags, children_ofs, children_n)


class ExistingEntry(Entry):
    def __init__(self, name, m, ofs):
        Entry.__init__(self, name)
        self._m = m
        self._ofs = ofs
        (self.dev, self.ctime, self.mtime, self.uid, self.gid,
         self.size, self.mode, self.gitmode, self.sha,
         self.flags, self.children_ofs, self.children_n
         ) = struct.unpack(INDEX_SIG, str(buffer(m, ofs, ENTLEN)))

    def repack(self):
        self._m[self._ofs:self._ofs+ENTLEN] = self.packed()

    def iter(self, name=None):
        dname = name
        if dname and not dname.endswith('/'):
            dname += '/'
        ofs = self.children_ofs
        #log('myname=%r\n' % self.name)
        assert(ofs <= len(self._m))
        for i in range(self.children_n):
            eon = self._m.find('\0', ofs)
            #log('eon=0x%x ofs=0x%x i=%d cn=%d\n' % (eon, ofs, i, self.children_n))
            assert(eon >= 0)
            assert(eon >= ofs)
            assert(eon > ofs)
            child = ExistingEntry(self.name + str(buffer(self._m, ofs, eon-ofs)),
                                  self._m, eon+1)
            if (not dname
                 or child.name.startswith(dname)
                 or child.name.endswith('/') and dname.startswith(child.name)):
                for e in child.iter(name=name):
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

    def __del__(self):
        self.close()

    def iter(self, name=None):
        if len(self.m):
            dname = name
            if dname and not dname.endswith('/'):
                dname += '/'
            root = ExistingEntry('/', self.m, len(self.m)-ENTLEN)
            for sub in root.iter(name=name):
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
            self.m = None
            self.writable = False

    def filter(self, prefixes):
        for (rp, path) in reduce_paths(prefixes):
            for e in self.iter(rp):
                assert(e.name.startswith(rp))
                name = path + e.name[len(rp):]
                yield (name, e)


# Read all the iters in order; when more than one iter has the same entry,
# the *later* iter in the list wins.  (ie. more recent iter entries replace
# older ones)
def _last_writer_wins_iter(iters):
    l = []
    for e in iters:
        it = iter(e)
        try:
            l.append([it.next(), it])
        except StopIteration:
            pass
    del iters  # to avoid accidents
    while l:
        l.sort()
        mv = l[0][0]
        mi = []
        for (i,(v,it)) in enumerate(l):
            #log('(%d) considering %d: %r\n' % (len(l), i, v))
            if v > mv:
                mv = v
                mi = [i]
            elif v == mv:
                mi.append(i)
        yield mv
        for i in mi:
            try:
                l[i][0] = l[i][1].next()
            except StopIteration:
                l[i] = None
        l = filter(None, l)


class Writer:
    def __init__(self, filename):
        self.stack = []
        self.f = None
        self.count = 0
        self.lastfile = None
        self.filename = None
        self.filename = filename = realpath(filename)
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
        while self.stack:
            self.add(''.join(self.stack[-1][0]), None)
        self._pop_to(None, [])
        self.f.flush()

    def close(self):
        self.flush()
        f = self.f
        self.f = None
        if f:
            f.close()
            os.rename(self.tmpname, self.filename)

    # FIXME: this function modifies 'entry' and can only pop a single level.
    # That means its semantics are basically crazy.
    def _pop_to(self, entry, edir):
        assert(len(self.stack) - len(edir) <= 1)
        while self.stack and self.stack[-1][0] > edir:
            #log('popping %r with %d entries (%d)\n' 
            #    % (''.join(self.stack[-1][0]), len(self.stack[-1][1]),
            #       len(self.stack)))
            p = self.stack.pop()
            entry.children_ofs = self.f.tell()
            entry.children_n = len(p[1])
            for e in p[1]:
                self._write(e)

    def _write(self, entry):
        #log('        writing %r\n' % entry.name)
        es = pathsplit(entry.name)
        self.f.write(es[-1] + '\0' + entry.packed())
        self.count += 1

    def _add(self, entry):
        es = pathsplit(entry.name)
        edir = es[:-1]
        self._pop_to(entry, edir)
        while len(self.stack) < len(edir):
            self.stack.append([es[:len(self.stack)+1], [], ()])
        if entry.name != '/':
            self.stack[-1][1].append(entry)
        else:
            self._write(entry)

    def add(self, name, st, hashgen = None):
        if self.lastfile:
            assert(cmp(self.lastfile, name) > 0) # reverse order only
        endswith = name.endswith('/')
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
            e = NewEntry(name, st.st_dev, int(st.st_ctime),
                         int(st.st_mtime), st.st_uid, st.st_gid,
                         st.st_size, st.st_mode, gitmode, sha, flags,
                         0, 0)
        else:
            assert(endswith)
            e = NewEntry(name, 0, 0, 0, 0, 0, 0, 0, gitmode, sha, flags, 0, 0)
        self.lastfile = name
        self._add(e)

    def add_ixentry(self, e):
        if self.lastfile and self.lastfile <= e.name:
            raise Error('%r must come before %r' 
                             % (e.name, self.lastfile))
        self.lastfile = e.name
        self._add(e)

    def new_reader(self):
        self.flush()
        return Reader(self.tmpname)


# like os.path.realpath, but doesn't follow a symlink for the last element.
# (ie. if 'p' itself is itself a symlink, this one won't follow it)
def realpath(p):
    try:
        st = os.lstat(p)
    except OSError:
        st = None
    if st and stat.S_ISLNK(st.st_mode):
        (dir, name) = os.path.split(p)
        dir = os.path.realpath(dir)
        out = os.path.join(dir, name)
    else:
        out = os.path.realpath(p)
    #log('realpathing:%r,%r\n' % (p, out))
    return out


def reduce_paths(paths):
    xpaths = []
    for p in paths:
        rp = realpath(p)
        try:
            st = os.lstat(rp)
            if stat.S_ISDIR(st.st_mode):
                rp = slashappend(rp)
                p = slashappend(p)
        except OSError, e:
            if e.errno != errno.ENOENT:
                raise
        xpaths.append((rp, p))
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

