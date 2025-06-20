
# pylint: disable=unused-import
from contextlib import ExitStack, nullcontext
from os import environb as environ
from os import fsdecode, fsencode
from shlex import quote
import dataclasses, os, sys, traceback

import bup_main


ver = sys.version_info

def hexstr(b):
    """Return hex string (not bytes as with hexlify) representation of b."""
    return b.hex()

if (ver.major, ver.minor) >= (3, 10):
    from itertools import pairwise
else:
    def pairwise(coll):
        it = iter(coll)
        x = next(it, None)
        for y in it:
            yield x, y
            x = y

if (ver.major, ver.minor) >= (3, 10):
    print_exception = traceback.print_exception
else:
    def print_exception(ex, **kwargs):
        # Only support 3.10+ style invocations, i.e. no value or tb
        return traceback.print_exception(type(ex), ex, ex.__traceback__,
                                         **kwargs)

def argv_bytes(x):
    """Return the original bytes passed to main() for an argv argument."""
    return fsencode(x)

def bytes_from_uint(i):
    return bytes((i,))

def getcwd():
    return fsencode(os.getcwd())

# Access argv directly, given https://bugs.python.org/issue35883

def get_argvb():
    "Return a new list containing the current process argv bytes."
    return bup_main.argv()

def get_argv():
    "Return a new list containing the current process argv strings."
    return [x.decode(errors='surrogateescape') for x in bup_main.argv()]

# Makes slots best effort
if (ver.major, ver.minor) >= (3, 10):
    dataclass = dataclasses.dataclass
else:
    def dataclass(*args, **kwargs):
        del kwargs['slots']
        return dataclasses.dataclass(*args, **kwargs)
