
from os import O_DIRECTORY, O_NOFOLLOW
import stat, os

from bup._helpers import open_noatime
from bup.helpers \
    import (add_error,
            debug1,
            finalized,
            resolve_parent,
            should_rx_exclude_path)
from bup import xstat
from bup.io import path_msg


# the use of fchdir() and lstat() is for two reasons:
#  - help out the kernel by not making it repeatedly look up the absolute path
#  - avoid race conditions caused by doing listdir() on a changing symlink


def _dirlist():
    l = []
    for n in os.listdir(b'.'):
        try:
            st = xstat.lstat(n)
        except OSError as e:
            add_error(Exception('%s: %s' % (resolve_parent(n), str(e))))
            continue
        if stat.S_ISDIR(st.st_mode):
            n += b'/'
        l.append((n,st))
    l.sort(reverse=True)
    return l

def _recursive_dirlist(prepend, xdev, bup_dir=None,
                       excluded_paths=None,
                       exclude_rxs=None,
                       xdev_exceptions=frozenset()):
    for (name,pst) in _dirlist():
        path = prepend + name
        npath = None
        if excluded_paths:
            npath = os.path.normpath(path)
            if npath in excluded_paths:
                debug1('Skipping %r: excluded.\n' % path_msg(path))
                continue
        if exclude_rxs and should_rx_exclude_path(path, exclude_rxs):
            continue
        if name[-1] != b'/'[0]:
            yield path, pst
            continue
        if bup_dir is not None and (npath or os.path.normpath(path)) == bup_dir:
            debug1('Skipping BUP_DIR.\n')
            continue
        if xdev is not None and pst.st_dev != xdev \
           and path not in xdev_exceptions:
            debug1('Skipping contents of %r: different filesystem.\n'
                   % path_msg(path))
            yield path, pst
            continue
        try:
            fd = open_noatime(name, O_NOFOLLOW | O_DIRECTORY)
        except OSError as e:
            add_error('%s: %s' % (prepend, e))
            yield path, pst
            continue
        with finalized(fd, os.close):
            os.fchdir(fd)
        yield from _recursive_dirlist(prepend=path, xdev=xdev,
                                      bup_dir=bup_dir,
                                      excluded_paths=excluded_paths,
                                      exclude_rxs=exclude_rxs,
                                      xdev_exceptions=xdev_exceptions)
        os.chdir(b'..')
        yield (path, pst)


def recursive_dirlist(paths, xdev, bup_dir=None,
                      excluded_paths=None,
                      exclude_rxs=None,
                      xdev_exceptions=frozenset()):
    startdir = open_noatime(b'.', O_NOFOLLOW | O_DIRECTORY)
    with finalized(startdir, os.close):
        try:
            assert not isinstance(paths, str)
            for path in paths:
                try:
                    pst = xstat.lstat(path)
                except OSError as e:
                    add_error('recursive_dirlist: %s' % e)
                    continue
                if not stat.S_ISDIR(pst.st_mode):
                    yield path, pst
                    continue
                try:
                    opened_pfile = open_noatime(path, O_NOFOLLOW | O_DIRECTORY)
                except OSError as e:
                    add_error(e)
                    continue
                with finalized(opened_pfile, os.close) as pfile:
                    xdev = pst.st_dev if xdev else None
                    os.fchdir(pfile)
                    prepend = os.path.join(path, b'')
                    yield from _recursive_dirlist(prepend=prepend, xdev=xdev,
                                                  bup_dir=bup_dir,
                                                  excluded_paths=excluded_paths,
                                                  exclude_rxs=exclude_rxs,
                                                  xdev_exceptions=xdev_exceptions)
                    os.fchdir(startdir)
                yield (prepend,pst)
        finally:
            os.fchdir(startdir)
