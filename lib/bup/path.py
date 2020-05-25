
from __future__ import absolute_import
import os, sys

# Eventually, if we physically move the source tree cmd/ to lib/, then
# we could use realpath here and save some stats...

fsencode = os.fsencode if sys.version_info[0] >= 3 else lambda x: x

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
