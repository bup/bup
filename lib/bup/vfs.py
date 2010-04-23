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


class FileReader:
    def __init__(self, node):
        self.n = node
        self.ofs = 0
        self.size = self.n.size()

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
        buf = self.n.readbytes(self.ofs, count)
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
    
    def readbytes(self, ofs, count):
        raise NotFile('%s is not a regular file' % self.name)
    
    def read(self, num = -1):
        if num < 0:
            num = self.size()
        return self.readbytes(0, num)
    
    
class File(Node):
    def _content(self):
        return cp().join(self.hash.encode('hex'))

    def open(self):
        return FileReader(self)
    
    def size(self):
        # FIXME inefficient.  If a file is chunked, we could just check
        # the offset + size of the very last chunk.
        return sum(len(blob) for blob in self._content())
    
    def readbytes(self, ofs, count):
        # FIXME inefficient.  If a file is chunked, we could choose to
        # read only the required chunks rather than joining the whole thing.
        buf = ''.join(self._content())
        return buf[ofs:ofs+count]
    

_symrefs = 0
class Symlink(File):
    def __init__(self, parent, name, hash):
        File.__init__(self, parent, name, 0120000, hash)

    def readlink(self):
        return self.read(1024)

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
        Symlink.__init__(self, parent, name, EMPTY_SHA)
        self.toname = toname
        
    def _content(self):
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
                self._subs[name] = Symlink(self, name, sha)
            else:
                self._subs[name] = File(self, name, mode, sha)
                

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
        

