
from __future__ import absolute_import, print_function
import errno, os, stat, struct, tempfile

from bup import compat, metadata, xstat
from bup._helpers import UINT_MAX, bytescmp
from bup.compat import range
from bup.helpers import (add_error, log, merge_iter, mmap_readwrite,
                         progress, qprogress, resolve_parent, slashappend)

EMPTY_SHA = b'\0' * 20
FAKE_SHA = b'\x01' * 20

INDEX_HDR = b'BUPI\0\0\0\7'

# Time values are handled as integer nanoseconds since the epoch in
# memory, but are written as xstat/metadata timespecs.  This behavior
# matches the existing metadata/xstat/.bupm code.

# Record times (mtime, ctime, atime) as xstat/metadata timespecs, and
# store all of the times in the index so they won't interfere with the
# forthcoming metadata cache.
INDEX_SIG = ('!'
             'Q'                # dev
             'Q'                # ino
             'Q'                # nlink
             'qQ'               # ctime_s, ctime_ns
             'qQ'               # mtime_s, mtime_ns
             'qQ'               # atime_s, atime_ns
             'Q'                # size
             'I'                # mode
             'I'                # gitmode
             '20s'              # sha
             'H'                # flags
             'Q'                # children_ofs
             'I'                # children_n
             'Q')               # meta_ofs

ENTLEN = struct.calcsize(INDEX_SIG)
FOOTER_SIG = '!Q'
FOOTLEN = struct.calcsize(FOOTER_SIG)

IX_EXISTS = 0x8000        # file exists on filesystem
IX_HASHVALID = 0x4000     # the stored sha1 matches the filesystem
IX_SHAMISSING = 0x2000    # the stored sha1 object doesn't seem to exist

class Error(Exception):
    pass


class MetaStoreReader:
    def __init__(self, filename):
        self._file = None
        self._file = open(filename, 'rb')

    def close(self):
        if self._file:
            self._file.close()
            self._file = None

    def __del__(self):
        self.close()

    def metadata_at(self, ofs):
        self._file.seek(ofs)
        return metadata.Metadata.read(self._file)


class MetaStoreWriter:
    # For now, we just append to the file, and try to handle any
    # truncation or corruption somewhat sensibly.

    def __init__(self, filename):
        # Map metadata hashes to bupindex.meta offsets.
        self._offsets = {}
        self._filename = filename
        self._file = None
        # FIXME: see how slow this is; does it matter?
        m_file = open(filename, 'ab+')
        try:
            m_file.seek(0)
            try:
                m_off = m_file.tell()
                m = metadata.Metadata.read(m_file)
                while m:
                    m_encoded = m.encode()
                    self._offsets[m_encoded] = m_off
                    m_off = m_file.tell()
                    m = metadata.Metadata.read(m_file)
            except EOFError:
                pass
            except:
                log('index metadata in %r appears to be corrupt' % filename)
                raise
        finally:
            m_file.close()
        self._file = open(filename, 'ab')

    def close(self):
        if self._file:
            self._file.close()
            self._file = None

    def __del__(self):
        # Be optimistic.
        self.close()

    def store(self, metadata):
        meta_encoded = metadata.encode(include_path=False)
        ofs = self._offsets.get(meta_encoded)
        if ofs:
            return ofs
        ofs = self._file.tell()
        self._file.write(meta_encoded)
        self._offsets[meta_encoded] = ofs
        return ofs


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


def _golevel(level, f, ename, newentry, metastore, tmax):
    # close nodes back up the tree
    assert(level)
    default_meta_ofs = metastore.store(metadata.Metadata())
    while ename[:len(level.ename)] != level.ename:
        n = BlankNewEntry(level.ename[-1], default_meta_ofs, tmax)
        n.flags |= IX_EXISTS
        (n.children_ofs,n.children_n) = level.write(f)
        level.parent.list.append(n)
        level = level.parent

    # create nodes down the tree
    while len(level.ename) < len(ename):
        level = Level(ename[:len(level.ename)+1], level)

    # are we in precisely the right place?
    assert(ename == level.ename)
    n = newentry or \
        BlankNewEntry(ename and level.ename[-1] or None, default_meta_ofs, tmax)
    (n.children_ofs,n.children_n) = level.write(f)
    if level.parent:
        level.parent.list.append(n)
    level = level.parent

    return level


class Entry:
    def __init__(self, basename, name, meta_ofs, tmax):
        assert basename is None or type(basename) == bytes
        assert name is None or type(name) == bytes
        self.basename = basename
        self.name = name
        self.meta_ofs = meta_ofs
        self.tmax = tmax
        self.children_ofs = 0
        self.children_n = 0

    def __repr__(self):
        return ("(%r,0x%04x,%d,%d,%d,%d,%d,%d,%s/%s,0x%04x,%d,0x%08x/%d)"
                % (self.name, self.dev, self.ino, self.nlink,
                   self.ctime, self.mtime, self.atime,
                   self.size, self.mode, self.gitmode,
                   self.flags, self.meta_ofs,
                   self.children_ofs, self.children_n))

    def packed(self):
        try:
            ctime = xstat.nsecs_to_timespec(self.ctime)
            mtime = xstat.nsecs_to_timespec(self.mtime)
            atime = xstat.nsecs_to_timespec(self.atime)
            return struct.pack(INDEX_SIG,
                               self.dev, self.ino, self.nlink,
                               ctime[0], ctime[1],
                               mtime[0], mtime[1],
                               atime[0], atime[1],
                               self.size, self.mode,
                               self.gitmode, self.sha, self.flags,
                               self.children_ofs, self.children_n,
                               self.meta_ofs)
        except (DeprecationWarning, struct.error) as e:
            log('pack error: %s (%r)\n' % (e, self))
            raise

    def stale(self, st, tstart, check_device=True):
        if self.size != st.st_size:
            return True
        if self.mtime != st.st_mtime:
            return True
        if self.sha == EMPTY_SHA:
            return True
        if not self.gitmode:
            return True
        if self.ctime != st.st_ctime:
            return True
        if self.ino != st.st_ino:
            return True
        if self.nlink != st.st_nlink:
            return True
        if not (self.flags & IX_EXISTS):
            return True
        if check_device and (self.dev != st.st_dev):
            return True
        # Check that the ctime's "second" is at or after tstart's.
        ctime_sec_in_ns = xstat.fstime_floor_secs(st.st_ctime) * 10**9
        if ctime_sec_in_ns >= tstart:
            return True
        return False

    def update_from_stat(self, st, meta_ofs):
        # Should only be called when the entry is stale(), and
        # invalidate() should almost certainly be called afterward.
        self.dev = st.st_dev
        self.ino = st.st_ino
        self.nlink = st.st_nlink
        self.ctime = st.st_ctime
        self.mtime = st.st_mtime
        self.atime = st.st_atime
        self.size = st.st_size
        self.mode = st.st_mode
        self.flags |= IX_EXISTS
        self.meta_ofs = meta_ofs
        self._fixup()

    def _fixup(self):
        self.mtime = self._fixup_time(self.mtime)
        self.ctime = self._fixup_time(self.ctime)

    def _fixup_time(self, t):
        if self.tmax != None and t > self.tmax:
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

    def _cmp(self, other):
        # Note reversed name ordering
        bc = bytescmp(other.name, self.name)
        if bc != 0:
            return bc
        vc = self.is_valid() - other.is_valid()
        if vc != 0:
            return vc
        fc = self.is_fake() - other.is_fake()
        if fc != 0:
            return fc
        return 0

    def __eq__(self, other):
        return self._cmp(other) == 0

    def __ne__():
        return self._cmp(other) != 0

    def __lt__(self, other):
        return self._cmp(other) < 0

    def __gt__(self, other):
        return self._cmp(other) > 0

    def __le__():
        return self._cmp(other) <= 0

    def __ge__():
        return self._cmp(other) >= 0

    def write(self, f):
        f.write(self.basename + b'\0' + self.packed())


class NewEntry(Entry):
    def __init__(self, basename, name, tmax, dev, ino, nlink,
                 ctime, mtime, atime,
                 size, mode, gitmode, sha, flags, meta_ofs,
                 children_ofs, children_n):
        Entry.__init__(self, basename, name, meta_ofs, tmax)
        (self.dev, self.ino, self.nlink, self.ctime, self.mtime, self.atime,
         self.size, self.mode, self.gitmode, self.sha,
         self.flags, self.children_ofs, self.children_n
         ) = (dev, ino, nlink, ctime, mtime, atime,
              size, mode, gitmode, sha, flags, children_ofs, children_n)
        self._fixup()


class BlankNewEntry(NewEntry):
    def __init__(self, basename, meta_ofs, tmax):
        NewEntry.__init__(self, basename, basename, tmax,
                          0, 0, 0, 0, 0, 0, 0, 0,
                          0, EMPTY_SHA, 0, meta_ofs, 0, 0)


class ExistingEntry(Entry):
    def __init__(self, parent, basename, name, m, ofs):
        Entry.__init__(self, basename, name, None, None)
        self.parent = parent
        self._m = m
        self._ofs = ofs
        (self.dev, self.ino, self.nlink,
         self.ctime, ctime_ns, self.mtime, mtime_ns, self.atime, atime_ns,
         self.size, self.mode, self.gitmode, self.sha,
         self.flags, self.children_ofs, self.children_n, self.meta_ofs
         ) = struct.unpack(INDEX_SIG, m[ofs : ofs + ENTLEN])
        self.atime = xstat.timespec_to_nsecs((self.atime, atime_ns))
        self.mtime = xstat.timespec_to_nsecs((self.mtime, mtime_ns))
        self.ctime = xstat.timespec_to_nsecs((self.ctime, ctime_ns))

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
        if dname and not dname.endswith(b'/'):
            dname += b'/'
        ofs = self.children_ofs
        assert(ofs <= len(self._m))
        assert(self.children_n <= UINT_MAX)  # i.e. python struct 'I'
        for i in range(self.children_n):
            eon = self._m.find(b'\0', ofs)
            assert(eon >= 0)
            assert(eon >= ofs)
            assert(eon > ofs)
            basename = self._m[ofs : ofs + (eon - ofs)]
            child = ExistingEntry(self, basename, self.name + basename,
                                  self._m, eon+1)
            if (not dname
                 or child.name.startswith(dname)
                 or child.name.endswith(b'/') and dname.startswith(child.name)):
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
        self.m = b''
        self.writable = False
        self.count = 0
        f = None
        try:
            f = open(filename, 'rb+')
        except IOError as e:
            if e.errno == errno.ENOENT:
                pass
            else:
                raise
        if f:
            b = f.read(len(INDEX_HDR))
            if b != INDEX_HDR:
                log('warning: %s: header: expected %r, got %r\n'
                                 % (filename, INDEX_HDR, b))
            else:
                st = os.fstat(f.fileno())
                if st.st_size:
                    self.m = mmap_readwrite(f)
                    self.writable = True
                    self.count = struct.unpack(FOOTER_SIG,
                                               self.m[st.st_size - FOOTLEN
                                                      : st.st_size])[0]

    def __del__(self):
        self.close()

    def __len__(self):
        return int(self.count)

    def forward_iter(self):
        ofs = len(INDEX_HDR)
        while ofs+ENTLEN <= len(self.m)-FOOTLEN:
            eon = self.m.find(b'\0', ofs)
            assert(eon >= 0)
            assert(eon >= ofs)
            assert(eon > ofs)
            basename = self.m[ofs : ofs + (eon - ofs)]
            yield ExistingEntry(None, basename, basename, self.m, eon+1)
            ofs = eon + 1 + ENTLEN

    def iter(self, name=None, wantrecurse=None):
        if len(self.m) > len(INDEX_HDR)+ENTLEN:
            dname = name
            if dname and not dname.endswith(b'/'):
                dname += b'/'
            root = ExistingEntry(None, b'/', b'/',
                                 self.m, len(self.m)-FOOTLEN-ENTLEN)
            for sub in root.iter(name=name, wantrecurse=wantrecurse):
                yield sub
            if not dname or dname == root.name:
                yield root

    def __iter__(self):
        return self.iter()

    def find(self, name):
        return next((e for e in self.iter(name, wantrecurse=lambda x : True)
                     if e.name == name),
                    None)

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
            any_entries = False
            for e in self.iter(rp, wantrecurse=wantrecurse):
                any_entries = True
                assert(e.name.startswith(rp))
                name = path + e.name[len(rp):]
                yield (name, e)
            if not any_entries:
                # Always return at least the top for each prefix.
                # Otherwise something like "save x/y" will produce
                # nothing if x is up to date.
                pe = self.find(rp)
                assert(pe)
                name = path + pe.name[len(rp):]
                yield (name, pe)

# FIXME: this function isn't very generic, because it splits the filename
# in an odd way and depends on a terminating '/' to indicate directories.
def pathsplit(p):
    """Split a path into a list of elements of the file system hierarchy."""
    l = p.split(b'/')
    l = [i + b'/' for i in l[:-1]] + l[-1:]
    if l[-1] == b'':
        l.pop()  # extra blank caused by terminating '/'
    return l


class Writer:
    def __init__(self, filename, metastore, tmax):
        self.rootlevel = self.level = Level([], None)
        self.f = None
        self.count = 0
        self.lastfile = None
        self.filename = None
        self.filename = filename = resolve_parent(filename)
        self.metastore = metastore
        self.tmax = tmax
        (dir,name) = os.path.split(filename)
        ffd, self.tmpname = tempfile.mkstemp(b'.tmp', filename, dir)
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
            self.level = _golevel(self.level, self.f, [], None,
                                  self.metastore, self.tmax)
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
                             % (''.join(ename), ''.join(self.lastfile)))
        self.lastfile = ename
        self.level = _golevel(self.level, self.f, ename, entry,
                              self.metastore, self.tmax)

    def add(self, name, st, meta_ofs, hashgen = None):
        endswith = name.endswith(b'/')
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
            e = NewEntry(basename, name, self.tmax,
                         st.st_dev, st.st_ino, st.st_nlink,
                         st.st_ctime, st.st_mtime, st.st_atime,
                         st.st_size, st.st_mode, gitmode, sha, flags,
                         meta_ofs, 0, 0)
        else:
            assert(endswith)
            meta_ofs = self.metastore.store(metadata.Metadata())
            e = BlankNewEntry(basename, meta_ofs, self.tmax)
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


def _slashappend_or_add_error(p, caller):
    """Return p, after ensuring it has a single trailing slash if it names
    a directory, unless there's an OSError, in which case, call
    add_error() and return None."""
    try:
        st = os.lstat(p)
    except OSError as e:
        add_error('%s: %s' % (caller, e))
        return None
    else:
        if stat.S_ISDIR(st.st_mode):
            return slashappend(p)
        return p


def unique_resolved_paths(paths):
    "Return a collection of unique resolved paths."
    rps = (_slashappend_or_add_error(resolve_parent(p), 'unique_resolved_paths')
           for p in paths)
    return frozenset((x for x in rps if x is not None))


def reduce_paths(paths):
    xpaths = []
    for p in paths:
        rp = _slashappend_or_add_error(resolve_parent(p), 'reduce_paths')
        if rp:
            xpaths.append((rp, slashappend(p) if rp.endswith(b'/') else p))
    xpaths.sort()

    paths = []
    prev = None
    for (rp, p) in xpaths:
        if prev and (prev == rp 
                     or (prev.endswith(b'/') and rp.startswith(prev))):
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
