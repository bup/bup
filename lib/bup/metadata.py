"""Metadata read/write support for bup."""

# Copyright (C) 2010 Rob Browning
#
# This code is covered under the terms of the GNU Library General
# Public License as described in the bup LICENSE file.

import errno, os, sys, stat, pwd, grp, struct, xattr, posix1e, re

from cStringIO import StringIO
from bup import vint
from bup.helpers import add_error, mkdirp, log, utime, lutime, lstat
import bup._helpers as _helpers

if _helpers.get_linux_file_attr:
    from bup._helpers import get_linux_file_attr, set_linux_file_attr

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
# FIXME: Consider caching users/groups.

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
    pos = result.rfind('/../')
    if(pos != -1):
        result = result[result.rfind('/../') + 4:]

    # Take everything after any remaining '../'.
    if result.startswith("../"):
        result = result[3:]

    # Remove any '/./' sequences.
    pos = result.find('/./')
    while pos != -1:
        result = result[0:pos] + '/' + result[pos + 3:]
        pos = result.find('/./')

    # Remove any leading '/'s.
    result = result.lstrip('/')

    # Replace '//' with '/' everywhere.
    pos = result.find('//')
    while pos != -1:
        result = result[0:pos] + '/' + result[pos + 2:]
        pos = result.find('//')

    # Take everything after any remaining './'.
    if result.startswith('./'):
        result = result[2:]

    # Take everything before any remaining '/.'.
    if result.endswith('/.'):
        result = result[:-2]

    if result == '' or result.endswith('/..'):
        result = '.'

    return result


def _risky_path(p):
    if p.startswith('/'):
        return True
    if p.find('/../') != -1:
        return True
    if p.startswith('../'):
        return True
    if p.endswith('/..'):
        return True
    return False


def _clean_up_extract_path(p):
    result = p.lstrip('/')
    if result == '':
        return '.'
    elif _risky_path(result):
        return None
    else:
        return result


def _normalize_ts(stamp):
    # For the purposes of normalization, t = s + ns.
    s = stamp[0]
    ns = stamp[1]
    if ns < 0 or ns >= 10**9:
        t = (s * 10**9) + ns
        if t == 0:
            return (0, 0)
        return ((t / 10**9), t % 10**9)
    return stamp


# These tags are currently conceptually private to Metadata, and they
# must be unique, and must *never* be changed.
_rec_tag_end = 0
_rec_tag_path = 1
_rec_tag_common = 2           # times, owner, group, type, perms, etc.
_rec_tag_symlink_target = 3
_rec_tag_posix1e_acl = 4      # getfacl(1), setfacl(1), etc.
_rec_tag_nfsv4_acl = 5        # intended to supplant posix1e acls?
_rec_tag_linux_attr = 6       # lsattr(1) chattr(1)
_rec_tag_linux_xattr = 7      # getfattr(1) setfattr(1)


class MetadataAcquisitionError(Exception):
    # Thrown when unable to extract any given bit of metadata from a path.
    pass


class MetadataApplicationError(Exception):
    # Thrown when unable to apply any given bit of metadata to a path.
    pass


class Metadata:
    # Metadata is stored as a sequence of tagged binary records.  Each
    # record will have some subset of add, encode, load, create, and
    # apply methods, i.e. _add_foo...

    ## Common records

    # Timestamps are (sec, ns), relative to 1970-01-01 00:00:00, ns
    # must be non-negative and < 10**9.

    def _add_common(self, path, st):
        self.mode = st.st_mode
        self.uid = st.st_uid
        self.gid = st.st_gid
        self.rdev = st.st_rdev
        self.atime = st.st_atime
        self.mtime = st.st_mtime
        self.ctime = st.st_ctime
        self.owner = pwd.getpwuid(st.st_uid)[0]
        self.group = grp.getgrgid(st.st_gid)[0]

    def _encode_common(self):
        atime = _normalize_ts(self.atime)
        mtime = _normalize_ts(self.mtime)
        ctime = _normalize_ts(self.ctime)
        result = vint.pack('VVsVsVvVvVvV',
                           self.mode,
                           self.uid,
                           self.owner,
                           self.gid,
                           self.group,
                           self.rdev,
                           atime[0],
                           atime[1],
                           mtime[0],
                           mtime[1],
                           ctime[0],
                           ctime[1])
        return result

    def _load_common_rec(self, port):
        data = vint.read_bvec(port)
        (self.mode,
         self.uid,
         self.owner,
         self.gid,
         self.group,
         self.rdev,
         self.atime,
         atime_ns,
         self.mtime,
         mtime_ns,
         self.ctime,
         ctime_ns) = vint.unpack('VVsVsVvVvVvV', data)
        self.atime = (self.atime, atime_ns)
        self.mtime = (self.mtime, mtime_ns)
        self.ctime = (self.ctime, ctime_ns)
        if self.atime[1] >= 10**9:
            path = ' for ' + self.path if self.path else ''
            log('bup: warning - normalizing bad atime%s\n' % (path))
            self.atime = _normalize_ts(self.atime)
        if self.mtime[1] >= 10**9:
            path = ' for ' + self.path if self.path else ''
            log('bup: warning - normalizing bad mtime%s\n' % (path))
            self.mtime = _normalize_ts(self.mtime)
        if self.ctime[1] >= 10**9:
            path = ' for ' + self.path if self.path else ''
            log('bup: warning - normalizing bad ctime%s\n' % (path))
            self.ctime = _normalize_ts(self.ctime)

    def _create_via_common_rec(self, path, create_symlinks=True):
        # If the path already exists and is a dir, try rmdir.
        # If the path already exists and is anything else, try unlink.
        st = None
        try:
            st = lstat(path)
        except IOError, e:
            if e.errno != errno.ENOENT:
                raise
        if st:
            if stat.S_ISDIR(st.st_mode):
                try:
                    os.rmdir(path)
                except OSError, e:
                    if e.errno == errno.ENOTEMPTY:
                        msg = 'refusing to overwrite non-empty dir' + path
                        raise Exception(msg)
                    raise
            else:
                os.unlink(path)

        if stat.S_ISREG(self.mode):
            os.mknod(path, 0600 | stat.S_IFREG)
        elif stat.S_ISDIR(self.mode):
            os.mkdir(path, 0700)
        elif stat.S_ISCHR(self.mode):
            os.mknod(path, 0600 | stat.S_IFCHR, self.rdev)
        elif stat.S_ISBLK(self.mode):
            os.mknod(path, 0600 | stat.S_IFBLK, self.rdev)
        elif stat.S_ISFIFO(self.mode):
            os.mknod(path, 0600 | stat.S_IFIFO)
        elif stat.S_ISLNK(self.mode):
            if(self.symlink_target and create_symlinks):
                os.symlink(self.symlink_target, path)
        # FIXME: S_ISDOOR, S_IFMPB, S_IFCMP, S_IFNWK, ... see stat(2).
        # Otherwise, do nothing.

    def _apply_common_rec(self, path, restore_numeric_ids=False):
        # FIXME: S_ISDOOR, S_IFMPB, S_IFCMP, S_IFNWK, ... see stat(2).
        if stat.S_ISLNK(self.mode):
            lutime(path, (self.atime, self.mtime))
        else:
            utime(path, (self.atime, self.mtime))
        if stat.S_ISREG(self.mode) \
                | stat.S_ISDIR(self.mode) \
                | stat.S_ISCHR(self.mode) \
                | stat.S_ISBLK(self.mode) \
                | stat.S_ISLNK(self.mode) \
                | stat.S_ISFIFO(self.mode):
            # Be safe.
            if _have_lchmod:
                os.lchmod(path, 0)
            elif not stat.S_ISLNK(self.mode):
                os.chmod(path, 0)

            # Don't try to restore owner unless we're root, and even
            # if asked, don't try to restore the owner or group if
            # it doesn't exist in the system db.
            uid = self.uid
            gid = self.gid
            if not restore_numeric_ids:
                if os.geteuid() == 0:
                    try:
                        uid = pwd.getpwnam(self.owner)[2]
                    except KeyError:
                        uid = -1
                        log('bup: ignoring unknown owner %s for "%s"\n'
                            % (self.owner, path))
                else:
                    uid = -1 # Not root; assume we can't change owner.
                try:
                    gid = grp.getgrnam(self.group)[2]
                except KeyError:
                    gid = -1
                    log('bup: ignoring unknown group %s for "%s"\n'
                        % (self.group, path))
            os.lchown(path, uid, gid)

            if _have_lchmod:
                os.lchmod(path, stat.S_IMODE(self.mode))
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
        if(stat.S_ISLNK(st.st_mode)):
            self.symlink_target = os.readlink(path)

    def _encode_symlink_target(self):
        return self.symlink_target

    def _load_symlink_target_rec(self, port):
        self.symlink_target = vint.read_bvec(port)


    ## POSIX1e ACL records

    # Recorded as a list:
    #   [txt_id_acl, num_id_acl]
    # or, if a directory:
    #   [txt_id_acl, num_id_acl, txt_id_default_acl, num_id_default_acl]
    # The numeric/text distinction only matters when reading/restoring
    # a stored record.
    def _add_posix1e_acl(self, path, st):
        if not stat.S_ISLNK(st.st_mode):
            try:
                if posix1e.has_extended(path):
                    acl = posix1e.ACL(file=path)
                    self.posix1e_acl = [acl, acl] # txt and num are the same
                    if stat.S_ISDIR(st.st_mode):
                        acl = posix1e.ACL(filedef=path)
                        self.posix1e_acl.extend([acl, acl])
            except EnvironmentError, e:
                if e.errno != errno.EOPNOTSUPP:
                    raise

    def _encode_posix1e_acl(self):
        # Encode as two strings (w/default ACL string possibly empty).
        if self.posix1e_acl:
            acls = self.posix1e_acl
            txt_flags = posix1e.TEXT_ABBREVIATE
            num_flags = posix1e.TEXT_ABBREVIATE | posix1e.TEXT_NUMERIC_IDS
            acl_reps = [acls[0].to_any_text('', '\n', txt_flags),
                        acls[1].to_any_text('', '\n', num_flags)]
            if(len(acls) < 3):
                acl_reps += ['', '']
            else:
                acl_reps.append(acls[2].to_any_text('', '\n', txt_flags))
                acl_reps.append(acls[3].to_any_text('', '\n', num_flags))
            return vint.pack('ssss',
                             acl_reps[0], acl_reps[1], acl_reps[2], acl_reps[3])
        else:
            return None

    def _load_posix1e_acl_rec(self, port):
        data = vint.read_bvec(port)
        acl_reps = vint.unpack('ssss', data)
        if(acl_reps[2] == ''):
            acl_reps = acl_reps[:2]
        self.posix1e_acl = [posix1e.ACL(x) for x in acl_reps]

    def _apply_posix1e_acl_rec(self, path, restore_numeric_ids=False):
        if(self.posix1e_acl):
            acls = self.posix1e_acl
            if(len(acls) > 2):
                if restore_numeric_ids:
                    acls[3].applyto(path, posix1e.ACL_TYPE_DEFAULT)
                else:
                    acls[2].applyto(path, posix1e.ACL_TYPE_DEFAULT)
            if restore_numeric_ids:
                acls[1].applyto(path, posix1e.ACL_TYPE_ACCESS)
            else:
                acls[0].applyto(path, posix1e.ACL_TYPE_ACCESS)


    ## Linux attributes (lsattr(1), chattr(1))

    def _add_linux_attr(self, path, st):
        if stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode):
            attr = get_linux_file_attr(path)
            if(attr != 0):
                self.linux_attr = get_linux_file_attr(path)

    def _encode_linux_attr(self):
        if self.linux_attr:
            return vint.pack('V', self.linux_attr)
        else:
            return None

    def _load_linux_attr_rec(self, port):
        data = vint.read_bvec(port)
        self.linux_attr = vint.unpack('V', data)[0]

    def _apply_linux_attr_rec(self, path, restore_numeric_ids=False):
        if(self.linux_attr):
            set_linux_file_attr(path, self.linux_attr)


    ## Linux extended attributes (getfattr(1), setfattr(1))

    def _add_linux_xattr(self, path, st):
        try:
            self.linux_xattr = xattr.get_all(path, nofollow=True)
        except EnvironmentError, e:
            if e.errno != errno.EOPNOTSUPP:
                raise

    def _encode_linux_xattr(self):
        if self.linux_xattr:
            result = vint.pack('V', len(items))
            for name, value in self.attrs:
                result += vint.pack('ss', name, value)
            return result
        else:
            return None

    def _load_linux_xattr_rec(self, file):
        data = vint.read_bvec(file)
        memfile = StringIO(data)
        result = []
        for i in range(vint.read_vuint(memfile)):
            key = vint.read_bvec(memfile)
            value = vint.read_bvec(memfile)
            result.append((key, value))
        self.linux_xattr = result

    def _apply_linux_xattr_rec(self, path, restore_numeric_ids=False):
        if(self.linux_xattr):
            for k, v in self.linux_xattr:
                xattr.set(path, k, v, nofollow=True)

    def __init__(self):
        # optional members
        self.path = None
        self.symlink_target = None
        self.linux_attr = None
        self.linux_xattr = None
        self.posix1e_acl = None
        self.posix1e_acl_default = None

    def write(self, port, include_path=True):
        records = [(_rec_tag_path, self._encode_path())] if include_path else []
        records.extend([(_rec_tag_common, self._encode_common()),
                        (_rec_tag_symlink_target, self._encode_symlink_target()),
                        (_rec_tag_posix1e_acl, self._encode_posix1e_acl()),
                        (_rec_tag_linux_attr, self._encode_linux_attr()),
                        (_rec_tag_linux_xattr, self._encode_linux_xattr())])
        for tag, data in records:
            if data:
                vint.write_vuint(port, tag)
                vint.write_bvec(port, data)
        vint.write_vuint(port, _rec_tag_end)

    @staticmethod
    def read(port):
        # This method should either: return a valid Metadata object;
        # throw EOFError if there was nothing at all to read; throw an
        # Exception if a valid object could not be read completely.
        tag = vint.read_vuint(port)
        try: # From here on, EOF is an error.
            result = Metadata()
            while(True): # only exit is error (exception) or _rec_tag_end
                if tag == _rec_tag_path:
                    result._load_path_rec(port)
                elif tag == _rec_tag_common:
                    result._load_common_rec(port)
                elif tag == _rec_tag_symlink_target:
                    result._load_symlink_target_rec(port)
                elif tag == _rec_tag_posix1e_acl:
                    result._load_posix1e_acl(port)
                elif tag ==_rec_tag_nfsv4_acl:
                    result._load_nfsv4_acl_rec(port)
                elif tag == _rec_tag_linux_attr:
                    result._load_linux_attr_rec(port)
                elif tag == _rec_tag_linux_xattr:
                    result._load_linux_xattr_rec(port)
                elif tag == _rec_tag_end:
                    return result
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
            raise Exception('Metadata.apply_to_path() called with no path');
        num_ids = restore_numeric_ids
        try: # Later we may want to push this down and make it finer grained.
            self._apply_common_rec(path, restore_numeric_ids=num_ids)
            self._apply_posix1e_acl_rec(path, restore_numeric_ids=num_ids)
            self._apply_linux_attr_rec(path, restore_numeric_ids=num_ids)
            self._apply_linux_xattr_rec(path, restore_numeric_ids=num_ids)
        except Exception, e:
            raise MetadataApplicationError(str(e))


def from_path(path, archive_path=None, save_symlinks=True):
    result = Metadata()
    result.path = archive_path
    st = lstat(path)
    try: # Later we may want to push this down and make it finer grained.
        result._add_common(path, st)
        if(save_symlinks):
            result._add_symlink_target(path, st)
        result._add_posix1e_acl(path, st)
        result._add_linux_attr(path, st)
        result._add_linux_xattr(path, st)
    except Exception, e:
        raise MetadataAcquisitionError(str(e))
    return result


def save_tree(output_file, paths,
              recurse=False,
              write_paths=True,
              save_symlinks=True):
    for p in paths:
        safe_path = _clean_up_path_for_archive(p)
        if(safe_path != p):
            log('bup: archiving "%s" as "%s"\n' % (p, safe_path))

        # Handle path itself.
        try:
            m = from_path(p, archive_path=safe_path,
                          save_symlinks=save_symlinks)
        except MetadataAcquisitionError, e:
            add_error(e)

        if verbose:
            print >> sys.stderr, m.path
        m.write(output_file, include_path=write_paths)

        if recurse and os.path.isdir(p):
            for root, dirs, files in os.walk(p, onerror=add_error):
                items = files + dirs
                for sub_path in items:
                    full_path = os.path.join(root, sub_path)
                    safe_path = _clean_up_path_for_archive(full_path)
                    try:
                        m = from_path(full_path,
                                      archive_path=safe_path,
                                      save_symlinks=save_symlinks)
                    except MetadataAcquisitionError, e:
                        add_error(e)
                    if verbose:
                        print >> sys.stderr, m.path
                    m.write(output_file, include_path=write_paths)


def _set_up_path(meta, create_symlinks=True):
    # Allow directories to exist as a special case -- might have
    # been created by an earlier longer path.
    if meta.isdir():
        mkdirp(meta.path, 0700)
    else:
        parent = os.path.dirname(meta.path)
        if parent:
            mkdirp(parent, 0700)
            meta.create_path(meta.path, create_symlinks=create_symlinks)


class _ArchiveIterator:
    def next(self):
        try:
            return Metadata.read(self._file)
        except EOFError:
            raise StopIteration()

    def __iter__(self):
        return self

    def __init__(self, file):
        self._file = file


def display_archive(file):
    for meta in _ArchiveIterator(file):
        if verbose:
            print meta.path # FIXME
        else:
            print meta.path


def start_extract(file, create_symlinks=True):
    for meta in _ArchiveIterator(file):
        if verbose:
            print >> sys.stderr, meta.path
        xpath = _clean_up_extract_path(meta.path)
        if not xpath:
            add_error(Exception('skipping risky path "%s"' % meta.path))
        else:
            meta.path = xpath
            _set_up_path(meta, create_symlinks=create_symlinks)


def finish_extract(file, restore_numeric_ids=False):
    all_dirs = []
    for meta in _ArchiveIterator(file):
        xpath = _clean_up_extract_path(meta.path)
        if not xpath:
            add_error(Exception('skipping risky path "%s"' % dir.path))
        else:
            if os.path.isdir(meta.path):
                all_dirs.append(meta)
            else:
                if verbose:
                    print >> sys.stderr, meta.path
                try:
                    meta.apply_to_path(path=xpath,
                                       restore_numeric_ids=restore_numeric_ids)
                except MetadataApplicationError, e:
                    add_error(e)

    all_dirs.sort(key = lambda x : len(x.path), reverse=True)
    for dir in all_dirs:
        # Don't need to check xpath -- won't be in all_dirs if not OK.
        xpath = _clean_up_extract_path(dir.path)
        if verbose:
            print >> sys.stderr, dir.path
        try:
            dir.apply_to_path(path=xpath,
                              restore_numeric_ids=restore_numeric_ids)
        except MetadataApplicationError, e:
            add_error(e)


def extract(file, restore_numeric_ids=False, create_symlinks=True):
    # For now, just store all the directories and handle them last,
    # longest first.
    all_dirs = []
    for meta in _ArchiveIterator(file):
        xpath = _clean_up_extract_path(meta.path)
        if not xpath:
            add_error(Exception('skipping risky path "%s"' % meta.path))
        else:
            meta.path = xpath
            if verbose:
                print >> sys.stderr, '+', meta.path
            _set_up_path(meta, create_symlinks=create_symlinks)
            if os.path.isdir(meta.path):
                all_dirs.append(meta)
            else:
                if verbose:
                    print >> sys.stderr, '=', meta.path
                try:
                    meta.apply_to_path(restore_numeric_ids=restore_numeric_ids)
                except MetadataApplicationError, e:
                    add_error(e)
    all_dirs.sort(key = lambda x : len(x.path), reverse=True)
    for dir in all_dirs:
        # Don't need to check xpath -- won't be in all_dirs if not OK.
        xpath = _clean_up_extract_path(meta.path)
        if verbose:
            print >> sys.stderr, '=', meta.path
        # Shouldn't have to check for risky paths here (omitted above).
        try:
            dir.apply_to_path(path=dir.path,
                              restore_numeric_ids=restore_numeric_ids)
        except MetadataApplicationError, e:
            add_error(e)
