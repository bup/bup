"""Metadata read/write support for bup."""

# Copyright (C) 2010 Rob Browning
#
# This code is covered under the terms of the GNU Library General
# Public License as described in the bup LICENSE file.

from __future__ import absolute_import, print_function
from binascii import hexlify
from copy import deepcopy
from errno import EACCES, EINVAL, ENOTTY, ENOSYS, EOPNOTSUPP
from io import BytesIO
from time import gmtime, strftime
import errno, os, sys, stat, time, pwd, grp, socket, struct

from bup import compat, vint, xstat
from bup.compat import py_maj
from bup.drecurse import recursive_dirlist
from bup.helpers import add_error, mkdirp, log, is_superuser, format_filesize
from bup.io import path_msg
from bup.pwdgrp import pwd_from_uid, pwd_from_name, grp_from_gid, grp_from_name
from bup.xstat import utime, lutime

xattr = None
if sys.platform.startswith('linux'):
    # prefer python-pyxattr (it's a lot faster), but fall back to python-xattr
    # as the two are incompatible and only one can be installed on a system
    try:
        import xattr
    except ImportError:
        log('Warning: Linux xattr support missing; install python-pyxattr.\n')
    if xattr and getattr(xattr, 'get_all', None) is None:
        try:
            from xattr import pyxattr_compat as xattr
            if not isinstance(xattr.NS_USER, bytes):
                xattr = None
        except ImportError:
            xattr = None
        if xattr is None:
            log('Warning: python-xattr module is too old; '
                'upgrade or install python-pyxattr instead.\n')

try:
    from bup._helpers import read_acl, apply_acl
except ImportError:
    if not (sys.platform.startswith('cygwin') or
            sys.platform.startswith('darwin') or
            sys.platform.startswith('netbsd')):
        log('Warning: POSIX ACL support missing; recompile with libacl1-dev/libacl-devel.\n')
    read_acl = apply_acl = None

try:
    from bup._helpers import get_linux_file_attr, set_linux_file_attr
except ImportError:
    # No need for a warning here; the only reason they won't exist is that we're
    # not on Linux, in which case files don't have any linux attrs anyway, so
    # lacking the functions isn't a problem.
    get_linux_file_attr = set_linux_file_attr = None


# See the bup_get_linux_file_attr() comments.
_suppress_linux_file_attr = \
    sys.byteorder == 'big' and struct.calcsize('@l') > struct.calcsize('@i')

def check_linux_file_attr_api():
    global get_linux_file_attr, set_linux_file_attr
    if not (get_linux_file_attr or set_linux_file_attr):
        return
    if _suppress_linux_file_attr:
        log('Warning: Linux attr support disabled (see "bup help index").\n')
        get_linux_file_attr = set_linux_file_attr = None


# WARNING: the metadata encoding is *not* stable yet.  Caveat emptor!

# Q: Consider hardlink support?
# Q: Is it OK to store raw linux attr (chattr) flags?
# Q: Can anything other than S_ISREG(x) or S_ISDIR(x) support posix1e ACLs?
# Q: Is the application of posix1e has_extended() correct?
# Q: Is one global --numeric-ids argument sufficient?
# Q: Do nfsv4 acls trump posix1e acls? (seems likely)
# Q: Add support for crtime -- ntfs, and (only internally?) ext*?

# FIXME: Fix relative/abs path detection/stripping wrt other platforms.
# FIXME: Add nfsv4 acl handling - see nfs4-acl-tools.
# FIXME: Consider other entries mentioned in stat(2) (S_IFDOOR, etc.).
# FIXME: Consider pack('vvvvsss', ...) optimization.

## FS notes:
#
# osx (varies between hfs and hfs+):
#   type - regular dir char block fifo socket ...
#   perms - rwxrwxrwxsgt
#   times - ctime atime mtime
#   uid
#   gid
#   hard-link-info (hfs+ only)
#   link-target
#   device-major/minor
#   attributes-osx see chflags
#   content-type
#   content-creator
#   forks
#
# ntfs
#   type - regular dir ...
#   times - creation, modification, posix change, access
#   hard-link-info
#   link-target
#   attributes - see attrib
#   ACLs
#   forks (alternate data streams)
#   crtime?
#
# fat
#   type - regular dir ...
#   perms - rwxrwxrwx (maybe - see wikipedia)
#   times - creation, modification, access
#   attributes - see attrib

verbose = 0

_have_lchmod = hasattr(os, 'lchmod')


def _clean_up_path_for_archive(p):
    # Not the most efficient approach.
    result = p

    # Take everything after any '/../'.
    pos = result.rfind(b'/../')
    if pos != -1:
        result = result[result.rfind(b'/../') + 4:]

    # Take everything after any remaining '../'.
    if result.startswith(b"../"):
        result = result[3:]

    # Remove any '/./' sequences.
    pos = result.find(b'/./')
    while pos != -1:
        result = result[0:pos] + b'/' + result[pos + 3:]
        pos = result.find(b'/./')

    # Remove any leading '/'s.
    result = result.lstrip(b'/')

    # Replace '//' with '/' everywhere.
    pos = result.find(b'//')
    while pos != -1:
        result = result[0:pos] + b'/' + result[pos + 2:]
        pos = result.find(b'//')

    # Take everything after any remaining './'.
    if result.startswith(b'./'):
        result = result[2:]

    # Take everything before any remaining '/.'.
    if result.endswith(b'/.'):
        result = result[:-2]

    if result == b'' or result.endswith(b'/..'):
        result = b'.'

    return result


def _risky_path(p):
    if p.startswith(b'/'):
        return True
    if p.find(b'/../') != -1:
        return True
    if p.startswith(b'../'):
        return True
    if p.endswith(b'/..'):
        return True
    return False


def _clean_up_extract_path(p):
    result = p.lstrip(b'/')
    if result == b'':
        return b'.'
    elif _risky_path(result):
        return None
    else:
        return result


# These tags are currently conceptually private to Metadata, and they
# must be unique, and must *never* be changed.
_rec_tag_end = 0
_rec_tag_path = 1
_rec_tag_common_v1 = 2 # times, user, group, type, perms, etc. (legacy/broken)
_rec_tag_symlink_target = 3
_rec_tag_posix1e_acl = 4      # getfacl(1), setfacl(1), etc.
_rec_tag_nfsv4_acl = 5        # intended to supplant posix1e? (unimplemented)
_rec_tag_linux_attr = 6       # lsattr(1) chattr(1)
_rec_tag_linux_xattr = 7      # getfattr(1) setfattr(1)
_rec_tag_hardlink_target = 8 # hard link target path
_rec_tag_common_v2 = 9 # times, user, group, type, perms, etc. (current)
_rec_tag_common_v3 = 10  # adds optional size to v2

_warned_about_attr_einval = None


class ApplyError(Exception):
    # Thrown when unable to apply any given bit of metadata to a path.
    pass


class Metadata:
    # Metadata is stored as a sequence of tagged binary records.  Each
    # record will have some subset of add, encode, load, create, and
    # apply methods, i.e. _add_foo...

    # We do allow an "empty" object as a special case, i.e. no
    # records.  One can be created by trying to write Metadata(), and
    # for such an object, read() will return None.  This is used by
    # "bup save", for example, as a placeholder in cases where
    # from_path() fails.

    # NOTE: if any relevant fields are added or removed, be sure to
    # update same_file() below.

    ## Common records

    # Timestamps are (sec, ns), relative to 1970-01-01 00:00:00, ns
    # must be non-negative and < 10**9.

    def _add_common(self, path, st):
        assert(st.st_uid >= 0)
        assert(st.st_gid >= 0)
        self.size = st.st_size
        self.uid = st.st_uid
        self.gid = st.st_gid
        self.atime = st.st_atime
        self.mtime = st.st_mtime
        self.ctime = st.st_ctime
        self.user = self.group = b''
        entry = pwd_from_uid(st.st_uid)
        if entry:
            self.user = entry.pw_name
        entry = grp_from_gid(st.st_gid)
        if entry:
            self.group = entry.gr_name
        self.mode = st.st_mode
        # Only collect st_rdev if we might need it for a mknod()
        # during restore.  On some platforms (i.e. kFreeBSD), it isn't
        # stable for other file types.  For example "cp -a" will
        # change it for a plain file.
        if stat.S_ISCHR(st.st_mode) or stat.S_ISBLK(st.st_mode):
            self.rdev = st.st_rdev
        else:
            self.rdev = 0

    def _same_common(self, other):
        """Return true or false to indicate similarity in the hardlink sense."""
        return self.uid == other.uid \
            and self.gid == other.gid \
            and self.rdev == other.rdev \
            and self.mtime == other.mtime \
            and self.ctime == other.ctime \
            and self.user == other.user \
            and self.group == other.group \
            and self.size == other.size

    def _encode_common(self):
        if not self.mode:
            return None
        atime = xstat.nsecs_to_timespec(self.atime)
        mtime = xstat.nsecs_to_timespec(self.mtime)
        ctime = xstat.nsecs_to_timespec(self.ctime)
        result = vint.pack('vvsvsvvVvVvVv',
                           self.mode,
                           self.uid,
                           self.user,
                           self.gid,
                           self.group,
                           self.rdev,
                           atime[0],
                           atime[1],
                           mtime[0],
                           mtime[1],
                           ctime[0],
                           ctime[1],
                           self.size if self.size is not None else -1)
        return result

    def _load_common_rec(self, port, version=3):
        if version == 3:
            # Added trailing size to v2, negative when None.
            unpack_fmt = 'vvsvsvvVvVvVv'
        elif version == 2:
            unpack_fmt = 'vvsvsvvVvVvV'
        elif version == 1:
            unpack_fmt = 'VVsVsVvVvVvV'
        else:
            raise Exception('unexpected common_rec version %d' % version)
        data = vint.read_bvec(port)
        values = vint.unpack(unpack_fmt, data)
        if version == 3:
            (self.mode, self.uid, self.user, self.gid, self.group,
             self.rdev,
             self.atime, atime_ns,
             self.mtime, mtime_ns,
             self.ctime, ctime_ns, size) = values
            if size >= 0:
                self.size = size
        else:
            (self.mode, self.uid, self.user, self.gid, self.group,
             self.rdev,
             self.atime, atime_ns,
             self.mtime, mtime_ns,
             self.ctime, ctime_ns) = values
        self.atime = xstat.timespec_to_nsecs((self.atime, atime_ns))
        self.mtime = xstat.timespec_to_nsecs((self.mtime, mtime_ns))
        self.ctime = xstat.timespec_to_nsecs((self.ctime, ctime_ns))

    def _recognized_file_type(self):
        return stat.S_ISREG(self.mode) \
            or stat.S_ISDIR(self.mode) \
            or stat.S_ISCHR(self.mode) \
            or stat.S_ISBLK(self.mode) \
            or stat.S_ISFIFO(self.mode) \
            or stat.S_ISSOCK(self.mode) \
            or stat.S_ISLNK(self.mode)

    def _create_via_common_rec(self, path, create_symlinks=True):
        if not self.mode:
            raise ApplyError('no metadata - cannot create path '
                             + path_msg(path))

        # If the path already exists and is a dir, try rmdir.
        # If the path already exists and is anything else, try unlink.
        st = None
        try:
            st = xstat.lstat(path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
        if st:
            if stat.S_ISDIR(st.st_mode):
                try:
                    os.rmdir(path)
                except OSError as e:
                    if e.errno in (errno.ENOTEMPTY, errno.EEXIST):
                        raise Exception('refusing to overwrite non-empty dir '
                                        + path_msg(path))
                    raise
            else:
                os.unlink(path)

        if stat.S_ISREG(self.mode):
            assert(self._recognized_file_type())
            fd = os.open(path, os.O_CREAT|os.O_WRONLY|os.O_EXCL, 0o600)
            os.close(fd)
        elif stat.S_ISDIR(self.mode):
            assert(self._recognized_file_type())
            os.mkdir(path, 0o700)
        elif stat.S_ISCHR(self.mode):
            assert(self._recognized_file_type())
            os.mknod(path, 0o600 | stat.S_IFCHR, self.rdev)
        elif stat.S_ISBLK(self.mode):
            assert(self._recognized_file_type())
            os.mknod(path, 0o600 | stat.S_IFBLK, self.rdev)
        elif stat.S_ISFIFO(self.mode):
            assert(self._recognized_file_type())
            os.mkfifo(path, 0o600 | stat.S_IFIFO)
        elif stat.S_ISSOCK(self.mode):
            try:
                os.mknod(path, 0o600 | stat.S_IFSOCK)
            except OSError as e:
                if e.errno in (errno.EINVAL, errno.EPERM):
                    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    s.bind(path)
                else:
                    raise
        elif stat.S_ISLNK(self.mode):
            assert(self._recognized_file_type())
            if self.symlink_target and create_symlinks:
                # on MacOS, symlink() permissions depend on umask, and there's
                # no way to chown a symlink after creating it, so we have to
                # be careful here!
                oldumask = os.umask((self.mode & 0o777) ^ 0o777)
                try:
                    os.symlink(self.symlink_target, path)
                finally:
                    os.umask(oldumask)
        # FIXME: S_ISDOOR, S_IFMPB, S_IFCMP, S_IFNWK, ... see stat(2).
        else:
            assert(not self._recognized_file_type())
            add_error('not creating "%s" with unrecognized mode "0x%x"\n'
                      % (path_msg(path), self.mode))

    def _apply_common_rec(self, path, restore_numeric_ids=False):
        if not self.mode:
            raise ApplyError('no metadata - cannot apply to ' + path_msg(path))

        # FIXME: S_ISDOOR, S_IFMPB, S_IFCMP, S_IFNWK, ... see stat(2).
        # EACCES errors at this stage are fatal for the current path.
        if lutime and stat.S_ISLNK(self.mode):
            try:
                lutime(path, (self.atime, self.mtime))
            except OSError as e:
                if e.errno == errno.EACCES:
                    raise ApplyError('lutime: %s' % e)
                else:
                    raise
        else:
            try:
                utime(path, (self.atime, self.mtime))
            except OSError as e:
                if e.errno == errno.EACCES:
                    raise ApplyError('utime: %s' % e)
                else:
                    raise

        uid = gid = -1 # By default, do nothing.
        if is_superuser():
            if self.uid is not None:
                uid = self.uid
            if self.gid is not None:
                gid = self.gid
            if not restore_numeric_ids:
                if self.uid != 0 and self.user:
                    entry = pwd_from_name(self.user)
                    if entry:
                        uid = entry.pw_uid
                if self.gid != 0 and self.group:
                    entry = grp_from_name(self.group)
                    if entry:
                        gid = entry.gr_gid
        else: # not superuser - only consider changing the group/gid
            user_gids = os.getgroups()
            if self.gid in user_gids:
                gid = self.gid
            if not restore_numeric_ids and self.gid != 0:
                # The grp might not exist on the local system.
                grps = filter(None, [grp_from_gid(x) for x in user_gids])
                if self.group in [x.gr_name for x in grps]:
                    g = grp_from_name(self.group)
                    if g:
                        gid = g.gr_gid

        if uid != -1 or gid != -1:
            try:
                os.lchown(path, uid, gid)
            except OSError as e:
                if e.errno == errno.EPERM:
                    add_error('lchown: %s' %  e)
                elif sys.platform.startswith('cygwin') \
                   and e.errno == errno.EINVAL:
                    add_error('lchown: unknown uid/gid (%d/%d) for %s'
                              %  (uid, gid, path_msg(path)))
                else:
                    raise

        if _have_lchmod:
            try:
                os.lchmod(path, stat.S_IMODE(self.mode))
            except errno.ENOSYS:  # Function not implemented
                pass
        elif not stat.S_ISLNK(self.mode):
            os.chmod(path, stat.S_IMODE(self.mode))


    ## Path records

    def _encode_path(self):
        if self.path:
            return vint.pack('s', self.path)
        else:
            return None

    def _load_path_rec(self, port):
        self.path = vint.unpack('s', vint.read_bvec(port))[0]


    ## Symlink targets

    def _add_symlink_target(self, path, st):
        try:
            if stat.S_ISLNK(st.st_mode):
                self.symlink_target = os.readlink(path)
        except OSError as e:
            add_error('readlink: %s' % e)

    def _encode_symlink_target(self):
        return self.symlink_target

    def _load_symlink_target_rec(self, port):
        target = vint.read_bvec(port)
        self.symlink_target = target
        if self.size is None:
            self.size = len(target)
        else:
            assert(self.size == len(target))


    ## Hardlink targets

    def _add_hardlink_target(self, target):
        self.hardlink_target = target

    def _same_hardlink_target(self, other):
        """Return true or false to indicate similarity in the hardlink sense."""
        return self.hardlink_target == other.hardlink_target

    def _encode_hardlink_target(self):
        return self.hardlink_target

    def _load_hardlink_target_rec(self, port):
        self.hardlink_target = vint.read_bvec(port)


    ## POSIX1e ACL records

    # Recorded as a list:
    #   [txt_id_acl, num_id_acl]
    # or, if a directory:
    #   [txt_id_acl, num_id_acl, txt_id_default_acl, num_id_default_acl]
    # The numeric/text distinction only matters when reading/restoring
    # a stored record.
    def _add_posix1e_acl(self, path, st):
        if not read_acl:
            return
        if not stat.S_ISLNK(st.st_mode):
            isdir = 1 if stat.S_ISDIR(st.st_mode) else 0
            self.posix1e_acl = read_acl(path, isdir)

    def _same_posix1e_acl(self, other):
        """Return true or false to indicate similarity in the hardlink sense."""
        return self.posix1e_acl == other.posix1e_acl

    def _encode_posix1e_acl(self):
        # Encode as two strings (w/default ACL string possibly empty).
        if self.posix1e_acl:
            acls = self.posix1e_acl
            if len(acls) == 2:
                return vint.pack('ssss', acls[0], acls[1], b'', b'')
            return vint.pack('ssss', acls[0], acls[1], acls[2], acls[3])
        else:
            return None

    def _load_posix1e_acl_rec(self, port):
        acl_rep = vint.unpack('ssss', vint.read_bvec(port))
        if acl_rep[2] == b'':
            acl_rep = acl_rep[:2]
        self.posix1e_acl = acl_rep

    def _apply_posix1e_acl_rec(self, path, restore_numeric_ids=False):
        if not self.posix1e_acl:
            return

        if not apply_acl:
            add_error("%s: can't restore ACLs; posix1e support missing.\n"
                      % path_msg(path))
            return

        try:
            acls = self.posix1e_acl
            offs = 1 if restore_numeric_ids else 0
            if len(acls) > 2:
                apply_acl(path, acls[offs], acls[offs + 2])
            else:
                apply_acl(path, acls[offs])
        except IOError as e:
            if e.errno == errno.EINVAL:
                # libacl returns with errno set to EINVAL if a user
                # (or group) doesn't exist
                raise ApplyError("POSIX1e ACL: can't create %r for %r"
                                 % (acls, path_msg(path)))
            elif e.errno == errno.EPERM or e.errno == errno.EOPNOTSUPP:
                raise ApplyError('POSIX1e ACL applyto: %s' % e)
            else:
                raise


    ## Linux attributes (lsattr(1), chattr(1))

    def _add_linux_attr(self, path, st):
        check_linux_file_attr_api()
        if not get_linux_file_attr: return
        if stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode):
            try:
                attr = get_linux_file_attr(path)
                if attr != 0:
                    self.linux_attr = attr
            except OSError as e:
                if e.errno == errno.EACCES:
                    add_error('read Linux attr: %s' % e)
                elif e.errno in (ENOTTY, ENOSYS, EOPNOTSUPP):
                    # Assume filesystem doesn't support attrs.
                    return
                elif e.errno == EINVAL:
                    global _warned_about_attr_einval
                    if not _warned_about_attr_einval:
                        log("Ignoring attr EINVAL;"
                            + " if you're not using ntfs-3g, please report: "
                            + path_msg(path) + '\n')
                        _warned_about_attr_einval = True
                    return
                else:
                    raise

    def _same_linux_attr(self, other):
        """Return true or false to indicate similarity in the hardlink sense."""
        return self.linux_attr == other.linux_attr

    def _encode_linux_attr(self):
        if self.linux_attr:
            return vint.pack('V', self.linux_attr)
        else:
            return None

    def _load_linux_attr_rec(self, port):
        data = vint.read_bvec(port)
        self.linux_attr = vint.unpack('V', data)[0]

    def _apply_linux_attr_rec(self, path, restore_numeric_ids=False):
        if self.linux_attr:
            check_linux_file_attr_api()
            if not set_linux_file_attr:
                add_error("%s: can't restore linuxattrs: "
                          "linuxattr support missing.\n" % path_msg(path))
                return
            try:
                set_linux_file_attr(path, self.linux_attr)
            except OSError as e:
                if e.errno in (EACCES, ENOTTY, EOPNOTSUPP, ENOSYS):
                    raise ApplyError('Linux chattr: %s (0x%s)'
                                     % (e, hex(self.linux_attr)))
                elif e.errno == EINVAL:
                    msg = "if you're not using ntfs-3g, please report"
                    raise ApplyError('Linux chattr: %s (0x%s) (%s)'
                                     % (e, hex(self.linux_attr), msg))
                else:
                    raise


    ## Linux extended attributes (getfattr(1), setfattr(1))

    def _add_linux_xattr(self, path, st):
        if not xattr: return
        try:
            self.linux_xattr = xattr.get_all(path, nofollow=True)
        except EnvironmentError as e:
            if e.errno != errno.EOPNOTSUPP:
                raise

    def _same_linux_xattr(self, other):
        """Return true or false to indicate similarity in the hardlink sense."""
        return self.linux_xattr == other.linux_xattr

    def _encode_linux_xattr(self):
        if self.linux_xattr:
            result = vint.pack('V', len(self.linux_xattr))
            for name, value in self.linux_xattr:
                result += vint.pack('ss', name, value)
            return result
        else:
            return None

    def _load_linux_xattr_rec(self, file):
        data = vint.read_bvec(file)
        memfile = BytesIO(data)
        result = []
        for i in range(vint.read_vuint(memfile)):
            key = vint.read_bvec(memfile)
            value = vint.read_bvec(memfile)
            result.append((key, value))
        self.linux_xattr = result

    def _apply_linux_xattr_rec(self, path, restore_numeric_ids=False):
        if not xattr:
            if self.linux_xattr:
                add_error("%s: can't restore xattr; xattr support missing.\n"
                          % path_msg(path))
            return
        if not self.linux_xattr:
            return
        try:
            existing_xattrs = set(xattr.list(path, nofollow=True))
        except IOError as e:
            if e.errno == errno.EACCES:
                raise ApplyError('xattr.set %r: %s' % (path_msg(path), e))
            else:
                raise
        for k, v in self.linux_xattr:
            if k not in existing_xattrs \
                    or v != xattr.get(path, k, nofollow=True):
                try:
                    xattr.set(path, k, v, nofollow=True)
                except IOError as e:
                    if e.errno == errno.EPERM \
                            or e.errno == errno.EOPNOTSUPP:
                        raise ApplyError('xattr.set %r: %s' % (path_msg(path), e))
                    else:
                        raise
            existing_xattrs -= frozenset([k])
        for k in existing_xattrs:
            try:
                xattr.remove(path, k, nofollow=True)
            except IOError as e:
                if e.errno in (errno.EPERM, errno.EACCES):
                    raise ApplyError('xattr.remove %r: %s' % (path_msg(path), e))
                else:
                    raise

    def __init__(self):
        self.mode = self.uid = self.gid = self.user = self.group = None
        self.atime = self.mtime = self.ctime = None
        # optional members
        self.path = None
        self.size = None
        self.symlink_target = None
        self.hardlink_target = None
        self.linux_attr = None
        self.linux_xattr = None
        self.posix1e_acl = None

    def __eq__(self, other):
        if not isinstance(other, Metadata): return False
        if self.mode != other.mode: return False
        if self.mtime != other.mtime: return False
        if self.ctime != other.ctime: return False
        if self.atime != other.atime: return False
        if self.path != other.path: return False
        if self.uid != other.uid: return False
        if self.gid != other.gid: return False
        if self.size != other.size: return False
        if self.user != other.user: return False
        if self.group != other.group: return False
        if self.symlink_target != other.symlink_target: return False
        if self.hardlink_target != other.hardlink_target: return False
        if self.linux_attr != other.linux_attr: return False
        if self.posix1e_acl != other.posix1e_acl: return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.mode,
                     self.mtime,
                     self.ctime,
                     self.atime,
                     self.path,
                     self.uid,
                     self.gid,
                     self.size,
                     self.user,
                     self.group,
                     self.symlink_target,
                     self.hardlink_target,
                     self.linux_attr,
                     self.posix1e_acl))

    def __repr__(self):
        result = ['<%s instance at %s' % (self.__class__, hex(id(self)))]
        if self.path is not None:
            result += ' path:' + repr(self.path)
        if self.mode is not None:
            result += ' mode: %o (%s)' % (self.mode, xstat.mode_str(self.mode))
        if self.uid is not None:
            result += ' uid:' + str(self.uid)
        if self.gid is not None:
            result += ' gid:' + str(self.gid)
        if self.user is not None:
            result += ' user:' + repr(self.user)
        if self.group is not None:
            result += ' group:' + repr(self.group)
        if self.size is not None:
            result += ' size:' + repr(self.size)
        for name, val in (('atime', self.atime),
                          ('mtime', self.mtime),
                          ('ctime', self.ctime)):
            if val is not None:
                result += ' %s:%r (%d)' \
                          % (name,
                             strftime('%Y-%m-%d %H:%M %z',
                                      gmtime(xstat.fstime_floor_secs(val))),
                             val)
        result += '>'
        return ''.join(result)

    def write(self, port, include_path=True):
        records = include_path and [(_rec_tag_path, self._encode_path())] or []
        records.extend([(_rec_tag_common_v3, self._encode_common()),
                        (_rec_tag_symlink_target,
                         self._encode_symlink_target()),
                        (_rec_tag_hardlink_target,
                         self._encode_hardlink_target()),
                        (_rec_tag_posix1e_acl, self._encode_posix1e_acl()),
                        (_rec_tag_linux_attr, self._encode_linux_attr()),
                        (_rec_tag_linux_xattr, self._encode_linux_xattr())])
        for tag, data in records:
            if data:
                vint.write_vuint(port, tag)
                vint.write_bvec(port, data)
        vint.write_vuint(port, _rec_tag_end)

    def encode(self, include_path=True):
        port = BytesIO()
        self.write(port, include_path)
        return port.getvalue()

    def copy(self):
        return deepcopy(self)

    @staticmethod
    def read(port):
        # This method should either return a valid Metadata object,
        # return None if there was no information at all (just a
        # _rec_tag_end), throw EOFError if there was nothing at all to
        # read, or throw an Exception if a valid object could not be
        # read completely.
        tag = vint.read_vuint(port)
        if tag == _rec_tag_end:
            return None
        try: # From here on, EOF is an error.
            result = Metadata()
            while True: # only exit is error (exception) or _rec_tag_end
                if tag == _rec_tag_path:
                    result._load_path_rec(port)
                elif tag == _rec_tag_common_v3:
                    result._load_common_rec(port, version=3)
                elif tag == _rec_tag_common_v2:
                    result._load_common_rec(port, version=2)
                elif tag == _rec_tag_symlink_target:
                    result._load_symlink_target_rec(port)
                elif tag == _rec_tag_hardlink_target:
                    result._load_hardlink_target_rec(port)
                elif tag == _rec_tag_posix1e_acl:
                    result._load_posix1e_acl_rec(port)
                elif tag == _rec_tag_linux_attr:
                    result._load_linux_attr_rec(port)
                elif tag == _rec_tag_linux_xattr:
                    result._load_linux_xattr_rec(port)
                elif tag == _rec_tag_end:
                    return result
                elif tag == _rec_tag_common_v1: # Should be very rare.
                    result._load_common_rec(port, version=1)
                else: # unknown record
                    vint.skip_bvec(port)
                tag = vint.read_vuint(port)
        except EOFError:
            raise Exception("EOF while reading Metadata")

    def isdir(self):
        return stat.S_ISDIR(self.mode)

    def create_path(self, path, create_symlinks=True):
        self._create_via_common_rec(path, create_symlinks=create_symlinks)

    def apply_to_path(self, path=None, restore_numeric_ids=False):
        # apply metadata to path -- file must exist
        if not path:
            path = self.path
        if not path:
            raise Exception('Metadata.apply_to_path() called with no path')
        if not self._recognized_file_type():
            add_error('not applying metadata to "%s"' % path_msg(path)
                      + ' with unrecognized mode "0x%x"\n' % self.mode)
            return
        num_ids = restore_numeric_ids
        for apply_metadata in (self._apply_common_rec,
                               self._apply_posix1e_acl_rec,
                               self._apply_linux_attr_rec,
                               self._apply_linux_xattr_rec):
            try:
                apply_metadata(path, restore_numeric_ids=num_ids)
            except ApplyError as e:
                add_error(e)

    def same_file(self, other):
        """Compare this to other for equivalency.  Return true if
        their information implies they could represent the same file
        on disk, in the hardlink sense.  Assume they're both regular
        files."""
        return self._same_common(other) \
            and self._same_hardlink_target(other) \
            and self._same_posix1e_acl(other) \
            and self._same_linux_attr(other) \
            and self._same_linux_xattr(other)


def from_path(path, statinfo=None, archive_path=None,
              save_symlinks=True, hardlink_target=None,
              normalized=False):
    """Return the metadata associated with the path.  When normalized is
    true, return the metadata appropriate for a typical save, which
    may or may not be all of it."""
    result = Metadata()
    result.path = archive_path
    st = statinfo or xstat.lstat(path)
    result._add_common(path, st)
    if save_symlinks:
        result._add_symlink_target(path, st)
    result._add_hardlink_target(hardlink_target)
    result._add_posix1e_acl(path, st)
    result._add_linux_attr(path, st)
    result._add_linux_xattr(path, st)
    if normalized:
        # Only store sizes for regular files and symlinks for now.
        if not (stat.S_ISREG(result.mode) or stat.S_ISLNK(result.mode)):
            result.size = None
    return result


def save_tree(output_file, paths,
              recurse=False,
              write_paths=True,
              save_symlinks=True,
              xdev=False):

    # Issue top-level rewrite warnings.
    for path in paths:
        safe_path = _clean_up_path_for_archive(path)
        if safe_path != path:
            log('archiving "%s" as "%s"\n'
                % (path_msg(path), path_msg(safe_path)))

    if not recurse:
        for p in paths:
            safe_path = _clean_up_path_for_archive(p)
            st = xstat.lstat(p)
            if stat.S_ISDIR(st.st_mode):
                safe_path += b'/'
            m = from_path(p, statinfo=st, archive_path=safe_path,
                          save_symlinks=save_symlinks)
            if verbose:
                print(m.path, file=sys.stderr)
            m.write(output_file, include_path=write_paths)
    else:
        start_dir = os.getcwd()
        try:
            for (p, st) in recursive_dirlist(paths, xdev=xdev):
                dirlist_dir = os.getcwd()
                os.chdir(start_dir)
                safe_path = _clean_up_path_for_archive(p)
                m = from_path(p, statinfo=st, archive_path=safe_path,
                              save_symlinks=save_symlinks)
                if verbose:
                    print(m.path, file=sys.stderr)
                m.write(output_file, include_path=write_paths)
                os.chdir(dirlist_dir)
        finally:
            os.chdir(start_dir)


def _set_up_path(meta, create_symlinks=True):
    # Allow directories to exist as a special case -- might have
    # been created by an earlier longer path.
    if meta.isdir():
        mkdirp(meta.path)
    else:
        parent = os.path.dirname(meta.path)
        if parent:
            mkdirp(parent)
        meta.create_path(meta.path, create_symlinks=create_symlinks)


all_fields = frozenset(['path',
                        'mode',
                        'link-target',
                        'rdev',
                        'size',
                        'uid',
                        'gid',
                        'user',
                        'group',
                        'atime',
                        'mtime',
                        'ctime',
                        'linux-attr',
                        'linux-xattr',
                        'posix1e-acl'])


def summary_bytes(meta, numeric_ids = False, classification = None,
                  human_readable = False):
    """Return bytes containing the "ls -l" style listing for meta.
    Classification may be "all", "type", or None."""
    user_str = group_str = size_or_dev_str = b'?'
    symlink_target = None
    if meta:
        name = meta.path
        mode_str = xstat.mode_str(meta.mode).encode('ascii')
        symlink_target = meta.symlink_target
        mtime_secs = xstat.fstime_floor_secs(meta.mtime)
        mtime_str = strftime('%Y-%m-%d %H:%M',
                             time.localtime(mtime_secs)).encode('ascii')
        if meta.user and not numeric_ids:
            user_str = meta.user
        elif meta.uid != None:
            user_str = str(meta.uid).encode()
        if meta.group and not numeric_ids:
            group_str = meta.group
        elif meta.gid != None:
            group_str = str(meta.gid).encode()
        if stat.S_ISCHR(meta.mode) or stat.S_ISBLK(meta.mode):
            if meta.rdev:
                size_or_dev_str = ('%d,%d' % (os.major(meta.rdev),
                                              os.minor(meta.rdev))).encode()
        elif meta.size != None:
            if human_readable:
                size_or_dev_str = format_filesize(meta.size).encode()
            else:
                size_or_dev_str = str(meta.size).encode()
        else:
            size_or_dev_str = b'-'
        if classification:
            classification_str = \
                xstat.classification_str(meta.mode,
                                         classification == 'all').encode()
    else:
        mode_str = b'?' * 10
        mtime_str = b'????-??-?? ??:??'
        classification_str = b'?'

    name = name or b''
    if classification:
        name += classification_str
    if symlink_target:
        name += b' -> ' + meta.symlink_target

    return b'%-10s %-11s %11s %16s %s' % (mode_str,
                                          user_str + b'/' + group_str,
                                          size_or_dev_str,
                                          mtime_str,
                                          name)


def detailed_bytes(meta, fields = None):
    # FIXME: should optional fields be omitted, or empty i.e. "rdev:
    # 0", "link-target:", etc.
    if not fields:
        fields = all_fields

    result = []
    if 'path' in fields:
        path = meta.path or b''
        result.append(b'path: ' + path)
    if 'mode' in fields:
        result.append(b'mode: %o (%s)'
                      % (meta.mode, xstat.mode_str(meta.mode).encode('ascii')))
    if 'link-target' in fields and stat.S_ISLNK(meta.mode):
        result.append(b'link-target: ' + meta.symlink_target)
    if 'rdev' in fields:
        if meta.rdev:
            result.append(b'rdev: %d,%d' % (os.major(meta.rdev),
                                            os.minor(meta.rdev)))
        else:
            result.append(b'rdev: 0')
    if 'size' in fields and meta.size is not None:
        result.append(b'size: %d' % meta.size)
    if 'uid' in fields:
        result.append(b'uid: %d' % meta.uid)
    if 'gid' in fields:
        result.append(b'gid: %d' % meta.gid)
    if 'user' in fields:
        result.append(b'user: ' + meta.user)
    if 'group' in fields:
        result.append(b'group: ' + meta.group)
    if 'atime' in fields:
        # If we don't have xstat.lutime, that means we have to use
        # utime(), and utime() has no way to set the mtime/atime of a
        # symlink.  Thus, the mtime/atime of a symlink is meaningless,
        # so let's not report it.  (That way scripts comparing
        # before/after won't trigger.)
        if xstat.lutime or not stat.S_ISLNK(meta.mode):
            result.append(b'atime: ' + xstat.fstime_to_sec_bytes(meta.atime))
        else:
            result.append(b'atime: 0')
    if 'mtime' in fields:
        if xstat.lutime or not stat.S_ISLNK(meta.mode):
            result.append(b'mtime: ' + xstat.fstime_to_sec_bytes(meta.mtime))
        else:
            result.append(b'mtime: 0')
    if 'ctime' in fields:
        result.append(b'ctime: ' + xstat.fstime_to_sec_bytes(meta.ctime))
    if 'linux-attr' in fields and meta.linux_attr:
        result.append(b'linux-attr: %x' % meta.linux_attr)
    if 'linux-xattr' in fields and meta.linux_xattr:
        for name, value in meta.linux_xattr:
            result.append(b'linux-xattr: %s -> %s' % (name, value))
    if 'posix1e-acl' in fields and meta.posix1e_acl:
        acl = meta.posix1e_acl[0]
        result.append(b'posix1e-acl: ' + acl + b'\n')
        if stat.S_ISDIR(meta.mode):
            def_acl = meta.posix1e_acl[2]
            result.append(b'posix1e-acl-default: ' + def_acl + b'\n')
    return b'\n'.join(result)


class _ArchiveIterator:
    def __next__(self):
        try:
            return Metadata.read(self._file)
        except EOFError:
            raise StopIteration()

    next = __next__

    def __iter__(self):
        return self

    def __init__(self, file):
        self._file = file


def display_archive(file, out):
    if verbose > 1:
        first_item = True
        for meta in _ArchiveIterator(file):
            if not first_item:
                out.write(b'\n')
            out.write(detailed_bytes(meta))
            out.write(b'\n')
            first_item = False
    elif verbose > 0:
        for meta in _ArchiveIterator(file):
            out.write(summary_bytes(meta))
            out.write(b'\n')
    elif verbose == 0:
        for meta in _ArchiveIterator(file):
            if not meta.path:
                log('bup: no metadata path, but asked to only display path'
                    ' (increase verbosity?)')
                sys.exit(1)
            out.write(meta.path)
            out.write(b'\n')


def start_extract(file, create_symlinks=True):
    for meta in _ArchiveIterator(file):
        if not meta: # Hit end record.
            break
        if verbose:
            print(path_msg(meta.path), file=sys.stderr)
        xpath = _clean_up_extract_path(meta.path)
        if not xpath:
            add_error(Exception('skipping risky path "%s"'
                                % path_msg(meta.path)))
        else:
            meta.path = xpath
            _set_up_path(meta, create_symlinks=create_symlinks)


def finish_extract(file, restore_numeric_ids=False):
    all_dirs = []
    for meta in _ArchiveIterator(file):
        if not meta: # Hit end record.
            break
        xpath = _clean_up_extract_path(meta.path)
        if not xpath:
            add_error(Exception('skipping risky path "%s"'
                                % path_msg(meta.path)))
        else:
            if os.path.isdir(meta.path):
                all_dirs.append(meta)
            else:
                if verbose:
                    print(path_msg(meta.path), file=sys.stderr)
                meta.apply_to_path(path=xpath,
                                   restore_numeric_ids=restore_numeric_ids)
    all_dirs.sort(key = lambda x : len(x.path), reverse=True)
    for dir in all_dirs:
        # Don't need to check xpath -- won't be in all_dirs if not OK.
        xpath = _clean_up_extract_path(dir.path)
        if verbose:
            print(path_msg(dir.path), file=sys.stderr)
        dir.apply_to_path(path=xpath, restore_numeric_ids=restore_numeric_ids)


def extract(file, restore_numeric_ids=False, create_symlinks=True):
    # For now, just store all the directories and handle them last,
    # longest first.
    all_dirs = []
    for meta in _ArchiveIterator(file):
        if not meta: # Hit end record.
            break
        xpath = _clean_up_extract_path(meta.path)
        if not xpath:
            add_error(Exception('skipping risky path "%s"'
                                % path_msg(meta.path)))
        else:
            meta.path = xpath
            if verbose:
                print('+', path_msg(meta.path), file=sys.stderr)
            _set_up_path(meta, create_symlinks=create_symlinks)
            if os.path.isdir(meta.path):
                all_dirs.append(meta)
            else:
                if verbose:
                    print('=', path_msg(meta.path), file=sys.stderr)
                meta.apply_to_path(restore_numeric_ids=restore_numeric_ids)
    all_dirs.sort(key = lambda x : len(x.path), reverse=True)
    for dir in all_dirs:
        # Don't need to check xpath -- won't be in all_dirs if not OK.
        xpath = _clean_up_extract_path(dir.path)
        if verbose:
            print('=', path_msg(xpath), file=sys.stderr)
        # Shouldn't have to check for risky paths here (omitted above).
        dir.apply_to_path(path=dir.path,
                          restore_numeric_ids=restore_numeric_ids)
