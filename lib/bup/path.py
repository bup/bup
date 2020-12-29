
from os import environb as environ
import os

from bup.compat import environ

# Eventually, if we physically move the source tree cmd/ to lib/, then
# we could use realpath here and save some stats...

fsencode = os.fsencode

_libdir = os.path.abspath(os.path.dirname(fsencode(__file__)) + b'/..')
_resdir = _libdir
_exedir = os.path.abspath(_libdir + b'/cmd')
_exe = os.path.join(_exedir, b'bup')


def exe():
    return _exe

def exedir():
    return _exedir

cmddir = exedir

def libdir():
    return _libdir

def resource_path(subdir=b''):
    return os.path.join(_resdir, subdir)

def defaultrepo():
    repo = environ.get(b'BUP_DIR')
    if repo:
        return repo
    return os.path.expanduser(b'~/.bup')

def cached(*what):
    """Return the cache path to what (path joined). Currently just a
    defaultrepo() subdir."""
    return os.path.join(defaultrepo(), *what)

def indexcache(identifier):
    return cached(b'index-cache', identifier)
