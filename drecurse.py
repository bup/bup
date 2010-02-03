import stat
from helpers import *

try:
    O_LARGEFILE = os.O_LARGEFILE
except AttributeError:
    O_LARGEFILE = 0


class OsFile:
    def __init__(self, path):
        self.fd = None
        self.fd = os.open(path, os.O_RDONLY|O_LARGEFILE|os.O_NOFOLLOW)
        
    def __del__(self):
        if self.fd:
            fd = self.fd
            self.fd = None
            os.close(fd)

    def fchdir(self):
        os.fchdir(self.fd)


# the use of fchdir() and lstat() are for two reasons:
#  - help out the kernel by not making it repeatedly look up the absolute path
#  - avoid race conditions caused by doing listdir() on a changing symlink
def dirlist(path):
    l = []
    try:
        OsFile(path).fchdir()
    except OSError, e:
        add_error(e)
        return l
    for n in os.listdir('.'):
        try:
            st = os.lstat(n)
        except OSError, e:
            add_error(Exception('in %s: %s' % (index.realpath(path), str(e))))
            continue
        if stat.S_ISDIR(st.st_mode):
            n += '/'
        l.append((os.path.join(path, n), st))
    l.sort(reverse=True)
    return l


def _recursive_dirlist(path, xdev):
    olddir = OsFile('.')
    for (path,pst) in dirlist(path):
        if xdev != None and pst.st_dev != xdev:
            log('Skipping %r: different filesystem.\n' % path)
            continue
        if stat.S_ISDIR(pst.st_mode):
            for i in _recursive_dirlist(path, xdev=xdev):
                yield i
        yield (path,pst)
    olddir.fchdir()


def _matchlen(a,b):
    bi = iter(b)
    count = 0
    for ai in a:
        try:
            if bi.next() == ai:
                count += 1
        except StopIteration:
            break
    return count


def recursive_dirlist(paths, xdev):
    assert(type(paths) != type(''))
    last = ()
    for path in paths:
        ps = pathsplit(path)
        while _matchlen(ps, last) < len(last):
            yield (''.join(last), None)
            last.pop()
        pst = os.lstat(path)
        if xdev:
            xdev = pst.st_dev
        else:
            xdev = None
        if stat.S_ISDIR(pst.st_mode):
            for i in _recursive_dirlist(path, xdev=xdev):
                yield i
        yield (path,pst)
        last = ps[:-1]


