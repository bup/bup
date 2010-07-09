import os, re, stat, time
from bup import git
from helpers import *

EMPTY_SHA='\0'*20

_cp = None
def cp():
    global _cp
    if not _cp:
        _cp = git.CatPipe()
    return _cp

class NodeError(Exception):
    pass
class NoSuchFile(NodeError):
    pass
class NotDir(NodeError):
    pass
class NotFile(NodeError):
    pass
class TooManySymlinks(NodeError):
    pass


def _treeget(hash):
    it = cp().get(hash.encode('hex'))
    type = it.next()
    assert(type == 'tree')
    return git._treeparse(''.join(it))


def _tree_decode(hash):
    tree = [(int(name,16),stat.S_ISDIR(int(mode,8)),sha)
            for (mode,name,sha)
            in _treeget(hash)]
    assert(tree == list(sorted(tree)))
    return tree


def _chunk_len(hash):
    return sum(len(b) for b in cp().join(hash.encode('hex')))


def _last_chunk_info(hash):
    tree = _tree_decode(hash)
    assert(tree)
    (ofs,isdir,sha) = tree[-1]
    if isdir:
        (subofs, sublen) = _last_chunk_info(sha)
        return (ofs+subofs, sublen)
    else:
        return (ofs, _chunk_len(sha))


def _total_size(hash):
    (lastofs, lastsize) = _last_chunk_info(hash)
    return lastofs + lastsize


def _chunkiter(hash, startofs):
    assert(startofs >= 0)
    tree = _tree_decode(hash)

    # skip elements before startofs
    for i in xrange(len(tree)):
        if i+1 >= len(tree) or tree[i+1][0] > startofs:
            break
    first = i

    # iterate through what's left
    for i in xrange(first, len(tree)):
        (ofs,isdir,sha) = tree[i]
        skipmore = startofs-ofs
        if skipmore < 0:
            skipmore = 0
        if isdir:
            for b in _chunkiter(sha, skipmore):
                yield b
        else:
            yield ''.join(cp().join(sha.encode('hex')))[skipmore:]


class _ChunkReader:
    def __init__(self, hash, isdir, startofs):
        if isdir:
            self.it = _chunkiter(hash, startofs)
            self.blob = None
        else:
            self.it = None
            self.blob = ''.join(cp().join(hash.encode('hex')))[startofs:]
        self.ofs = startofs

    def next(self, size):
        out = ''
        while len(out) < size:
            if self.it and not self.blob:
                try:
                    self.blob = self.it.next()
                except StopIteration:
                    self.it = None
            if self.blob:
                want = size - len(out)
                out += self.blob[:want]
                self.blob = self.blob[want:]
            if not self.it:
                break
        log('next(%d) returned %d\n' % (size, len(out)))
        self.ofs += len(out)
        return out


class _FileReader:
    def __init__(self, hash, size, isdir):
        self.hash = hash
        self.ofs = 0
        self.size = size
        self.isdir = isdir
        self.reader = None

    def seek(self, ofs):
        if ofs > self.size:
            self.ofs = self.size
        elif ofs < 0:
            self.ofs = 0
        else:
            self.ofs = ofs

    def tell(self):
        return self.ofs

    def read(self, count = -1):
        if count < 0:
            count = self.size - self.ofs
        if not self.reader or self.reader.ofs != self.ofs:
            self.reader = _ChunkReader(self.hash, self.isdir, self.ofs)
        try:
            buf = self.reader.next(count)
        except:
            self.reader = None
            raise  # our offsets will be all screwed up otherwise
        self.ofs += len(buf)
        return buf


class Node:
    def __init__(self, parent, name, mode, hash):
        self.parent = parent
        self.name = name
        self.mode = mode
        self.hash = hash
        self.ctime = self.mtime = self.atime = 0
        self._subs = None
        
    def __cmp__(a, b):
        return cmp(a.name or None, b.name or None)
    
    def __iter__(self):
        return iter(self.subs())
    
    def fullname(self):
        if self.parent:
            return os.path.join(self.parent.fullname(), self.name)
        else:
            return self.name
    
    def _mksubs(self):
        self._subs = {}
        
    def subs(self):
        if self._subs == None:
            self._mksubs()
        return sorted(self._subs.values())
        
    def sub(self, name):
        if self._subs == None:
            self._mksubs()
        ret = self._subs.get(name)
        if not ret:
            raise NoSuchFile("no file %r in %r" % (name, self.name))
        return ret

    def top(self):
        if self.parent:
            return self.parent.top()
        else:
            return self

    def _lresolve(self, parts):
        #log('_lresolve %r in %r\n' % (parts, self.name))
        if not parts:
            return self
        (first, rest) = (parts[0], parts[1:])
        if first == '.':
            return self._lresolve(rest)
        elif first == '..':
            if not self.parent:
                raise NoSuchFile("no parent dir for %r" % self.name)
            return self.parent._lresolve(rest)
        elif rest:
            return self.sub(first)._lresolve(rest)
        else:
            return self.sub(first)

    def lresolve(self, path):
        start = self
        if path.startswith('/'):
            start = self.top()
            path = path[1:]
        parts = re.split(r'/+', path or '.')
        if not parts[-1]:
            parts[-1] = '.'
        #log('parts: %r %r\n' % (path, parts))
        return start._lresolve(parts)

    def resolve(self, path):
        return self.lresolve(path).lresolve('')
    
    def nlinks(self):
        if self._subs == None:
            self._mksubs()
        return 1

    def size(self):
        return 0

    def open(self):
        raise NotFile('%s is not a regular file' % self.name)


class File(Node):
    def __init__(self, parent, name, mode, hash, bupmode):
        Node.__init__(self, parent, name, mode, hash)
        self.bupmode = bupmode
        self._cached_size = None
        self._filereader = None
        
    def open(self):
        # You'd think FUSE might call this only once each time a file is
        # opened, but no; it's really more of a refcount, and it's called
        # once per read().  Thus, it's important to cache the filereader
        # object here so we're not constantly re-seeking.
        if not self._filereader:
            self._filereader = _FileReader(self.hash, self.size(),
                                           self.bupmode == git.BUP_CHUNKED)
        self._filereader.seek(0)
        return self._filereader
    
    def size(self):
        if self._cached_size == None:
            log('<<<<File.size() is calculating...\n')
            if self.bupmode == git.BUP_CHUNKED:
                self._cached_size = _total_size(self.hash)
            else:
                self._cached_size = _chunk_len(self.hash)
            log('<<<<File.size() done.\n')
        return self._cached_size


_symrefs = 0
class Symlink(File):
    def __init__(self, parent, name, hash, bupmode):
        File.__init__(self, parent, name, 0120000, hash, bupmode)

    def size(self):
        return len(self.readlink())

    def readlink(self):
        return ''.join(cp().join(self.hash.encode('hex')))

    def dereference(self):
        global _symrefs
        if _symrefs > 100:
            raise TooManySymlinks('too many levels of symlinks: %r'
                                  % self.fullname())
        _symrefs += 1
        try:
            return self.parent.lresolve(self.readlink())
        finally:
            _symrefs -= 1

    def _lresolve(self, parts):
        return self.dereference()._lresolve(parts)
    

class FakeSymlink(Symlink):
    def __init__(self, parent, name, toname):
        Symlink.__init__(self, parent, name, EMPTY_SHA, git.BUP_NORMAL)
        self.toname = toname
        
    def readlink(self):
        return self.toname
    

class Dir(Node):
    def _mksubs(self):
        self._subs = {}
        it = cp().get(self.hash.encode('hex'))
        type = it.next()
        if type == 'commit':
            del it
            it = cp().get(self.hash.encode('hex') + ':')
            type = it.next()
        assert(type == 'tree')
        for (mode,mangled_name,sha) in git._treeparse(''.join(it)):
            mode = int(mode, 8)
            name = mangled_name
            (name,bupmode) = git.demangle_name(mangled_name)
            if bupmode == git.BUP_CHUNKED:
                mode = 0100644
            if stat.S_ISDIR(mode):
                self._subs[name] = Dir(self, name, mode, sha)
            elif stat.S_ISLNK(mode):
                self._subs[name] = Symlink(self, name, sha, bupmode)
            else:
                self._subs[name] = File(self, name, mode, sha, bupmode)
                

class CommitList(Node):
    def __init__(self, parent, name, hash):
        Node.__init__(self, parent, name, 040000, hash)
        
    def _mksubs(self):
        self._subs = {}
        revs = list(git.rev_list(self.hash.encode('hex')))
        for (date, commit) in revs:
            l = time.localtime(date)
            ls = time.strftime('%Y-%m-%d-%H%M%S', l)
            commithex = '.' + commit.encode('hex')
            n1 = Dir(self, commithex, 040000, commit)
            n2 = FakeSymlink(self, ls, commithex)
            n1.ctime = n1.mtime = n2.ctime = n2.mtime = date
            self._subs[commithex] = n1
            self._subs[ls] = n2
            latest = max(revs)
        if latest:
            (date, commit) = latest
            commithex = '.' + commit.encode('hex')
            n2 = FakeSymlink(self, 'latest', commithex)
            n2.ctime = n2.mtime = date
            self._subs['latest'] = n2

    
class RefList(Node):
    def __init__(self, parent):
        Node.__init__(self, parent, '/', 040000, EMPTY_SHA)
        
    def _mksubs(self):
        self._subs = {}
        for (name,sha) in git.list_refs():
            if name.startswith('refs/heads/'):
                name = name[11:]
                date = git.rev_get_date(sha.encode('hex'))
                n1 = CommitList(self, name, sha)
                n1.ctime = n1.mtime = date
                self._subs[name] = n1
        

