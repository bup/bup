
from __future__ import absolute_import
import os


# Eventually, if we physically move the source tree cmd/ to lib/, then
# we could use realpath here and save some stats...

_libdir = os.path.abspath(os.path.dirname(__file__) + '/..')
_exedir = os.path.abspath(_libdir + '/cmd')
_exe = os.path.join(_exedir, 'bup')


def exe():
    return _exe

def exedir():
    return _exedir

cmddir = exedir

def libdir():
    return _libdir
