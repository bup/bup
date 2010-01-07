#!/usr/bin/env python2.5
import sys, re, errno, stat, tempfile, struct, mmap
import options
from helpers import *

INDEX_SIG = '!IIIIIQ20sH'
ENTLEN = struct.calcsize(INDEX_SIG)

IX_EXISTS = 0x8000
IX_HASHVALID = 0x4000


class OsFile:
    def __init__(self, path):
        self.fd = None
        self.fd = os.open(path, os.O_RDONLY|os.O_LARGEFILE|os.O_NOFOLLOW)
        #self.st = os.fstat(self.fd)
        
    def __del__(self):
        if self.fd:
            fd = self.fd
            self.fd = None
            os.close(fd)

    def fchdir(self):
        os.fchdir(self.fd)


class IxEntry:
    def __init__(self, name, m, ofs):
        self._m = m
        self._ofs = ofs
        self.name = str(name)
        (self.dev, self.ctime, self.mtime, self.uid, self.gid,
         self.size, self.sha,
         self.flags) = struct.unpack(INDEX_SIG, buffer(m, ofs, ENTLEN))

    def __repr__(self):
        return ("(%s,0x%04x,%d,%d,%d,%d,%d,0x%04x)" 
                % (self.name, self.dev,
                   self.ctime, self.mtime, self.uid, self.gid,
                   self.size, self.flags))

    def pack(self):
        return struct.pack(INDEX_SIG, self.dev, self.ctime, self.mtime,
                           self.uid, self.gid, self.size, self.sha,
                           self.flags)

    def repack(self):
        self._m[self._ofs:self._ofs+ENTLEN] = self.pack()

    def from_stat(self, st):
        old = (self.dev, self.ctime, self.mtime,
               self.uid, self.gid, self.size)
        new = (st.st_dev, int(st.st_ctime), int(st.st_mtime),
               st.st_uid, st.st_gid, st.st_size)
        self.dev = st.st_dev
        self.ctime = int(st.st_ctime)
        self.mtime = int(st.st_mtime)
        self.uid = st.st_uid
        self.gid = st.st_gid
        self.size = st.st_size
        self.flags |= IX_EXISTS
        if old != new:
            self.flags &= ~IX_HASHVALID
            return 1  # dirty
        else:
            return 0  # not dirty
            

class IndexReader:
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
            st = os.fstat(f.fileno())
        if f and st.st_size:
            self.m = mmap.mmap(f.fileno(), 0,
                               mmap.MAP_SHARED, mmap.PROT_READ|mmap.PROT_WRITE)
            f.close()  # map will persist beyond file close
            self.writable = True

    def __iter__(self):
        ofs = 0
        while ofs < len(self.m):
            eon = self.m.find('\0', ofs)
            assert(eon >= 0)
            yield IxEntry(buffer(self.m, ofs, eon-ofs),
                          self.m, eon+1)
            ofs = eon + 1 + ENTLEN

    def save(self):
        if self.writable:
            self.m.flush()


def ix_encode(st, sha, flags):
    return struct.pack(INDEX_SIG, st.st_dev, int(st.st_ctime),
                       int(st.st_mtime), st.st_uid, st.st_gid,
                       st.st_size, sha, flags)


class IndexWriter:
    def __init__(self, filename):
        self.f = None
        self.lastfile = None
        self.filename = None
        self.filename = filename = os.path.realpath(filename)
        (dir,name) = os.path.split(filename)
        (ffd,self.tmpname) = tempfile.mkstemp('.tmp', filename, dir)
        self.f = os.fdopen(ffd, 'wb', 65536)

    def __del__(self):
        self.abort()

    def abort(self):
        f = self.f
        self.f = None
        if f:
            f.close()
            os.unlink(self.tmpname)

    def close(self):
        f = self.f
        self.f = None
        if f:
            f.close()
            os.rename(self.tmpname, self.filename)

    def add(self, name, st):
        #log('ADDING %r\n' % name)
        if self.lastfile:
            assert(cmp(self.lastfile, name) > 0) # reverse order only
        self.lastfile = name
        data = name + '\0' + ix_encode(st, '\0'*20, IX_EXISTS|IX_HASHVALID)
        self.f.write(data)

    def add_ixentry(self, e):
        if opt.fake_valid:
            e.flags |= IX_HASHVALID
        if self.lastfile:
            assert(cmp(self.lastfile, e.name) > 0) # reverse order only
        self.lastfile = e.name
        data = e.name + '\0' + e.pack()
        self.f.write(data)

    def new_reader(self):
        self.f.flush()
        return IndexReader(self.tmpname)


saved_errors = []
def add_error(e):
    saved_errors.append(e)
    log('\n%s\n' % e)


# the use of fchdir() and lstat() are for two reasons:
#  - help out the kernel by not making it repeatedly look up the absolute path
#  - avoid race conditions caused by doing listdir() on a changing symlink
def handle_path(ri, wi, dir, name, pst, xdev):
    dirty = 0
    path = dir + name
    #log('handle_path(%r,%r)\n' % (dir, name))
    if stat.S_ISDIR(pst.st_mode):
        if opt.verbose == 1: # log dirs only
            sys.stdout.write('%s\n' % path)
            sys.stdout.flush()
        try:
            OsFile(name).fchdir()
        except OSError, e:
            add_error(Exception('in %s: %s' % (dir, str(e))))
            return 0
        try:
            try:
                ld = os.listdir('.')
                #log('* %r: %r\n' % (name, ld))
            except OSError, e:
                add_error(Exception('in %s: %s' % (path, str(e))))
                return 0
            lds = []
            for p in ld:
                try:
                    st = os.lstat(p)
                except OSError, e:
                    add_error(Exception('in %s: %s' % (path, str(e))))
                    continue
                if xdev != None and st.st_dev != xdev:
                    log('Skipping %r: different filesystem.\n' 
                        % os.path.realpath(p))
                    continue
                if stat.S_ISDIR(st.st_mode):
                    p += '/'
                lds.append((p, st))
            for p,st in reversed(sorted(lds)):
                dirty += handle_path(ri, wi, path, p, st, xdev)
        finally:
            os.chdir('..')
    #log('endloop: ri.cur:%r path:%r\n' % (ri.cur.name, path))
    while ri.cur and ri.cur.name > path:
        #log('ricur:%r path:%r\n' % (ri.cur, path))
        if dir and ri.cur.name.startswith(dir):
            #log('    --- deleting\n')
            ri.cur.flags &= ~(IX_EXISTS | IX_HASHVALID)
            ri.cur.repack()
            dirty += 1
        ri.next()
    if ri.cur and ri.cur.name == path:
        dirty += ri.cur.from_stat(pst)
        if dirty:
            #log('   --- updating %r\n' % path)
            ri.cur.repack()
        ri.next()
    else:
        wi.add(path, pst)
        dirty += 1
    if opt.verbose > 1:  # all files, not just dirs
        sys.stdout.write('%s\n' % path)
        sys.stdout.flush()
    return dirty


def _next(i):
    try:
        return i.next()
    except StopIteration:
        return None


def merge_indexes(out, r1, r2):
    log('Merging indexes.\n')
    i1 = iter(r1)
    i2 = iter(r2)

    e1 = _next(i1)
    e2 = _next(i2)
    while e1 or e2:
        if e1 and (not e2 or e2.name < e1.name):
            if e1.flags & IX_EXISTS:
                out.add_ixentry(e1)
            e1 = _next(i1)
        elif e2 and (not e1 or e1.name < e2.name):
            if e2.flags & IX_EXISTS:
                out.add_ixentry(e2)
            e2 = _next(i2)
        elif e1.name == e2.name:
            assert(0)  # duplicate name? should never happen anymore.
            if e2.flags & IX_EXISTS:
                out.add_ixentry(e2)
            e1 = _next(i1)
            e2 = _next(i2)


class MergeGetter:
    def __init__(self, l):
        self.i = iter(l)
        self.cur = None
        self.next()

    def next(self):
        try:
            self.cur = self.i.next()
        except StopIteration:
            self.cur = None
        return self.cur


def update_index(path):
    ri = IndexReader(indexfile)
    wi = IndexWriter(indexfile)
    rpath = os.path.realpath(path)
    st = os.lstat(rpath)
    if opt.xdev:
        xdev = st.st_dev
    else:
        xdev = None
    f = OsFile('.')
    if rpath[-1] == '/':
        rpath = rpath[:-1]
    (dir, name) = os.path.split(rpath)
    if dir and dir[-1] != '/':
        dir += '/'
    if stat.S_ISDIR(st.st_mode) and (not rpath or rpath[-1] != '/'):
        name += '/'
    rig = MergeGetter(ri)
    OsFile(dir or '/').fchdir()
    dirty = handle_path(rig, wi, dir, name, st, xdev)

    # make sure all the parents of the updated path exist and are invalidated
    # if appropriate.
    while 1:
        (rpath, junk) = os.path.split(rpath)
        if not rpath:
            break
        elif rpath == '/':
            p = rpath
        else:
            p = rpath + '/'
        while rig.cur and rig.cur.name > p:
            #log('FINISHING: %r path=%r d=%r\n' % (rig.cur.name, p, dirty))
            rig.next()
        if rig.cur and rig.cur.name == p:
            if dirty:
                rig.cur.flags &= ~IX_HASHVALID
                rig.cur.repack()
        else:
            wi.add(p, os.lstat(p))
        if p == '/':
            break
    
    f.fchdir()
    ri.save()
    mi = IndexWriter(indexfile)
    merge_indexes(mi, ri, wi.new_reader())
    wi.abort()
    mi.close()


optspec = """
bup index [options...] <filenames...>
--
p,print    print index after updating
m,modified print only modified files (implies -p)
x,xdev,one-file-system  don't cross filesystem boundaries
fake-valid    mark all index entries as up-to-date even if they aren't
f,indexfile=  the name of the index file (default 'index')
s,status   print each filename with a status char (A/M/D) (implies -p)
v,verbose  increase log output (can be used more than once)
"""
o = options.Options('bup index', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

indexfile = opt.indexfile or 'index'

for path in extra:
    update_index(path)

if opt.fake_valid and not extra:
    mi = IndexWriter(indexfile)
    merge_indexes(mi, IndexReader(indexfile),
                  IndexWriter(indexfile).new_reader())
    mi.close()

if opt['print'] or opt.status or opt.modified:
    for ent in IndexReader(indexfile):
        if opt.modified and ent.flags & IX_HASHVALID:
            continue
        if opt.status:
            if not ent.flags & IX_EXISTS:
                print 'D ' + ent.name
            elif not ent.flags & IX_HASHVALID:
                print 'M ' + ent.name
            else:
                print '  ' + ent.name
        else:
            print ent.name
        #print repr(ent)

if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    exit(1)
