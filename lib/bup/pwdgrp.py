
from __future__ import absolute_import, print_function
import os, pwd, grp

from bup import compat  # to force the LC_CTYPE check
from bup.compat import py_maj
from bup.helpers import cache_key_value


# Using __slots__ makes these much smaller (even than a namedtuple)

class Passwd:
    """Drop in replacement for pwd's structure with bytes instead of strings."""
    __slots__ = ('pw_name', 'pw_passwd', 'pw_uid', 'pw_gid', 'pw_gecos',
                 'pw_dir', 'pw_shell')
    def __init__(self, name, passwd, uid, gid, gecos, dir, shell):
        assert type(name) == bytes
        assert type(passwd) == bytes
        assert type(gecos) == bytes
        assert type(dir) == bytes
        assert type(shell) == bytes
        (self.pw_name, self.pw_passwd, self.pw_uid, self.pw_gid,
         self.pw_gecos, self.pw_dir, self.pw_shell) = \
             name, passwd, uid, gid, gecos, dir, shell

def _passwd_from_py(py):
    if py_maj < 3:
        return py
    return Passwd(py.pw_name.encode('iso-8859-1'),
                  py.pw_passwd.encode("iso-8859-1"),
                  py.pw_uid, py.pw_gid,
                  py.pw_gecos.encode('iso-8859-1'),
                  py.pw_dir.encode('iso-8859-1'),
                  py.pw_shell.encode('iso-8859-1'))

def getpwuid(uid):
    return _passwd_from_py(pwd.getpwuid(uid))

def getpwnam(name):
    return _passwd_from_py(pwd.getpwnam(name))


class Group:
    """Drop in replacement for grp's structure with bytes instead of strings."""
    __slots__ = 'gr_name', 'gr_passwd', 'gr_gid', 'gr_mem'
    def __init__(self, name, passwd, gid, mem):
        assert type(name) == bytes
        assert type(passwd) == bytes
        for m in mem:
            assert type(m) == bytes
        self.gr_name, self.gr_passwd, self.gr_gid, self.gr_mem = \
            name, passwd, gid, mem

def _group_from_py(py):
    if py_maj < 3:
        return py
    return Group(py.gr_name.encode('iso-8859-1'),
                 py.gr_passwd.encode('iso-8859-1'),
                 py.gr_gid,
                 tuple(x.encode('iso-8859-1') for x in py.gr_mem))

def getgrgid(uid):
    return _group_from_py(grp.getgrgid(uid))

def getgrnam(name):
    return _group_from_py(grp.getgrnam(name))


_uid_to_pwd_cache = {}
_name_to_pwd_cache = {}

def pwd_from_uid(uid):
    """Return password database entry for uid (may be a cached value).
    Return None if no entry is found.
    """
    global _uid_to_pwd_cache, _name_to_pwd_cache
    entry, cached = cache_key_value(getpwuid, uid, _uid_to_pwd_cache)
    if entry and not cached:
        _name_to_pwd_cache[entry.pw_name] = entry
    return entry

def pwd_from_name(name):
    """Return password database entry for name (may be a cached value).
    Return None if no entry is found.
    """
    assert type(name) == bytes
    global _uid_to_pwd_cache, _name_to_pwd_cache
    entry, cached = cache_key_value(getpwnam, name, _name_to_pwd_cache)
    if entry and not cached:
        _uid_to_pwd_cache[entry.pw_uid] = entry
    return entry


_gid_to_grp_cache = {}
_name_to_grp_cache = {}

def grp_from_gid(gid):
    """Return password database entry for gid (may be a cached value).
    Return None if no entry is found.
    """
    global _gid_to_grp_cache, _name_to_grp_cache
    entry, cached = cache_key_value(getgrgid, gid, _gid_to_grp_cache)
    if entry and not cached:
        _name_to_grp_cache[entry.gr_name] = entry
    return entry


def grp_from_name(name):
    """Return password database entry for name (may be a cached value).
    Return None if no entry is found.
    """
    assert type(name) == bytes
    global _gid_to_grp_cache, _name_to_grp_cache
    entry, cached = cache_key_value(getgrnam, name, _name_to_grp_cache)
    if entry and not cached:
        _gid_to_grp_cache[entry.gr_gid] = entry
    return entry


_username = None
def username():
    """Get the user's login name."""
    global _username
    if not _username:
        uid = os.getuid()
        _username = pwd_from_uid(uid).pw_name or b'user%d' % uid
    return _username


_userfullname = None
def userfullname():
    """Get the user's full name."""
    global _userfullname
    if not _userfullname:
        uid = os.getuid()
        entry = pwd_from_uid(uid)
        if entry:
            _userfullname = entry.pw_gecos.split(b',')[0] or entry.pw_name
        if not _userfullname:
            _userfullname = b'user%d' % uid
    return _userfullname
