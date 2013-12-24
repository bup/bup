import stat, os
from bup.helpers import *
import bup.xstat as xstat

try:
    O_LARGEFILE = os.O_LARGEFILE
except AttributeError:
    O_LARGEFILE = 0
try:
    O_NOFOLLOW = os.O_NOFOLLOW
except AttributeError:
    O_NOFOLLOW = 0


# the use of fchdir() and lstat() is for two reasons:
#  - help out the kernel by not making it repeatedly look up the absolute path
#  - avoid race conditions caused by doing listdir() on a changing symlink
class OsFile:
    def __init__(self, path):
        self.fd = None
        self.fd = os.open(path, os.O_RDONLY|O_LARGEFILE|O_NOFOLLOW|os.O_NDELAY)
        
    def __del__(self):
        if self.fd:
            fd = self.fd
            self.fd = None
            os.close(fd)

    def fchdir(self):
        os.fchdir(self.fd)

    def stat(self):
        return xstat.fstat(self.fd)


_IFMT = stat.S_IFMT(0xffffffff)  # avoid function call in inner loop
def _dirlist():
    l = []
    for n in os.listdir('.'):
        try:
            st = xstat.lstat(n)
        except OSError, e:
            add_error(Exception('%s: %s' % (realpath(n), str(e))))
            continue
        if (st.st_mode & _IFMT) == stat.S_IFDIR:
            n += '/'
        l.append((n,st))
    l.sort(reverse=True)
    return l


def _recursive_dirlist(prepend, xdev, bup_dir=None,
                       excluded_paths=None,
                       exclude_rxs=None):
    for (name,pst) in _dirlist():
        path = prepend + name
        if excluded_paths:
            if os.path.normpath(path) in excluded_paths:
                debug1('Skipping %r: excluded.\n' % path)
                continue
        if exclude_rxs and should_rx_exclude_path(path, exclude_rxs):
            continue
        if name.endswith('/'):
            if bup_dir != None:
                if os.path.normpath(path) == bup_dir:
                    debug1('Skipping BUP_DIR.\n')
                    continue
            if xdev != None and pst.st_dev != xdev:
                debug1('Skipping contents of %r: different filesystem.\n' % path)
            else:
                try:
                    OsFile(name).fchdir()
                except OSError, e:
                    add_error('%s: %s' % (prepend, e))
                else:
                    for i in _recursive_dirlist(prepend=prepend+name, xdev=xdev,
                                                bup_dir=bup_dir,
                                                excluded_paths=excluded_paths,
                                                exclude_rxs=exclude_rxs):
                        yield i
                    os.chdir('..')
        yield (path, pst)


def recursive_dirlist(paths, xdev, bup_dir=None, excluded_paths=None,
                      exclude_rxs=None):
    startdir = OsFile('.')
    try:
        assert(type(paths) != type(''))
        for path in paths:
            try:
                pst = xstat.lstat(path)
                if stat.S_ISLNK(pst.st_mode):
                    yield (path, pst)
                    continue
            except OSError, e:
                add_error('recursive_dirlist: %s' % e)
                continue
            try:
                pfile = OsFile(path)
            except OSError, e:
                add_error(e)
                continue
            pst = pfile.stat()
            if xdev:
                xdev = pst.st_dev
            else:
                xdev = None
            if stat.S_ISDIR(pst.st_mode):
                pfile.fchdir()
                prepend = os.path.join(path, '')
                for i in _recursive_dirlist(prepend=prepend, xdev=xdev,
                                            bup_dir=bup_dir,
                                            excluded_paths=excluded_paths,
                                            exclude_rxs=exclude_rxs):
                    yield i
                startdir.fchdir()
            else:
                prepend = path
            yield (prepend,pst)
    except:
        try:
            startdir.fchdir()
        except:
            pass
        raise
