
from __future__ import absolute_import, print_function
import os, pwd, grp

from bup import _helpers
from bup.helpers import cache_key_value


# Using __slots__ makes these much smaller (even than a namedtuple)

class Passwd:
    """Drop in replacement for pwd's structure with bytes instead of strings."""
    __slots__ = ('pw_name', 'pw_passwd', 'pw_uid', 'pw_gid', 'pw_gecos',
                 'pw_dir', 'pw_shell')
    def __init__(self, name, passwd, uid, gid, gecos, dir, shell):
        assert isinstance(name, bytes)
        assert isinstance(passwd, bytes)
        assert isinstance(gecos, bytes)
        assert isinstance(dir, bytes)
        assert isinstance(shell, bytes)
        (self.pw_name, self.pw_passwd, self.pw_uid, self.pw_gid,
         self.pw_gecos, self.pw_dir, self.pw_shell) = \
             name, passwd, uid, gid, gecos, dir, shell

def getpwuid(uid):
    r = _helpers.getpwuid(uid)
    return Passwd(*r) if r else None

def getpwnam(name):
    assert isinstance(name, bytes)
    r = _helpers.getpwnam(name)
    return Passwd(*r) if r else None


class Group:
    """Drop in replacement for grp's structure with bytes instead of strings."""
    __slots__ = 'gr_name', 'gr_passwd', 'gr_gid', 'gr_mem'
    def __init__(self, name, passwd, gid, mem):
        assert isinstance(name, bytes)
        assert isinstance(passwd, bytes)
        for m in mem:
            assert isinstance(m, bytes)
        self.gr_name, self.gr_passwd, self.gr_gid, self.gr_mem = \
            name, passwd, gid, mem

def getgrgid(uid):
    r = _helpers.getgrgid(uid)
    return Group(*r) if r else None

def getgrnam(name):
    assert isinstance(name, bytes)
    r = _helpers.getgrnam(name)
    return Group(*r) if r else None


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
    assert isinstance(name, bytes)
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
    assert isinstance(name, bytes)
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
