
from os import O_DIRECTORY, O_NOFOLLOW, fsencode
from stat import S_ISDIR
import stat, os

from bup._helpers import open_noatime, openat_noatime
from bup.helpers \
    import (add_error,
            debug1,
            finalized,
            resolve_parent,
            should_rx_exclude_path)
from bup import xstat
from bup.io import path_msg


def _dirlist(fd):
    l = []
    for n in os.listdir(fd):
        try:
            st = xstat.lstat(n, dir_fd=fd)
        except OSError as e:
            add_error(Exception('%s: %s' % (resolve_parent(n), str(e))))
            continue
        l.append((fsencode(n + '/' if S_ISDIR(st.st_mode) else n), st))
    l.sort(reverse=True)
    return l

def _recursive_dirlist(prepend, dir_fd, xdev,
                       bup_dir=None,
                       excluded_paths=None,
                       exclude_rxs=None,
                       xdev_exceptions=frozenset()):
    for name, pst in _dirlist(dir_fd):
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
            sub_fd = openat_noatime(dir_fd, name, O_NOFOLLOW | O_DIRECTORY)
        except OSError as e:
            add_error('%s: %s' % (prepend, e))
            yield path, pst
            continue
        with finalized(sub_fd, os.close):
            yield from _recursive_dirlist(prepend=path,
                                          dir_fd=sub_fd,
                                          xdev=xdev,
                                          bup_dir=bup_dir,
                                          excluded_paths=excluded_paths,
                                          exclude_rxs=exclude_rxs,
                                          xdev_exceptions=xdev_exceptions)
        yield path, pst


def recursive_dirlist(paths, xdev, bup_dir=None,
                      excluded_paths=None,
                      exclude_rxs=None,
                      xdev_exceptions=frozenset()):
    for path in paths:
        assert isinstance(path, bytes), path
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
            path_fd = open_noatime(path, O_NOFOLLOW | O_DIRECTORY)
        except OSError as e:
            add_error(e)
            continue
        with finalized(path_fd, os.close):
            xdev = pst.st_dev if xdev else None
            prepend = path if path[-1] == b'/'[0] else path + b'/'
            yield from _recursive_dirlist(prepend=prepend,
                                          dir_fd=path_fd,
                                          xdev=xdev,
                                          bup_dir=bup_dir,
                                          excluded_paths=excluded_paths,
                                          exclude_rxs=exclude_rxs,
                                          xdev_exceptions=xdev_exceptions)
        yield prepend, pst
