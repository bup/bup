
# pylint: disable=unused-import
from contextlib import ExitStack, nullcontext
from os import environb as environ
from os import fsdecode, fsencode
from shlex import quote
import os, sys

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

class pending_raise:
    """If rethrow is true, rethrow ex (if any), unless the body throws.

    (Supports Python 2 compatibility.)

    """
    # This is completely vestigial, and should be removed
    def __init__(self, ex, rethrow=True):
        self.closed = False
        self.ex = ex
        self.rethrow = rethrow
    def __enter__(self):
        return None
    def __exit__(self, exc_type, exc_value, traceback):
        self.closed = True
        if not exc_type and self.ex and self.rethrow:
            raise self.ex
    def __del__(self):
        assert self.closed

def argv_bytes(x):
    """Return the original bytes passed to main() for an argv argument."""
    return fsencode(x)

def bytes_from_uint(i):
    return bytes((i,))

def bytes_from_byte(b):  # python > 2: b[3] returns ord('x'), not b'x'
    return bytes((b,))

def getcwd():
    return fsencode(os.getcwd())


try:
    import bup_main
except ModuleNotFoundError:
    bup_main = None

if bup_main:
    def get_argvb():
        "Return a new list containing the current process argv bytes."
        return bup_main.argv()
    def get_argv():
        "Return a new list containing the current process argv strings."
        return [x.decode(errors='surrogateescape') for x in bup_main.argv()]
else:
    def get_argvb():
        raise Exception('get_argvb requires the bup_main module');
    def get_argv():
        raise Exception('get_argv requires the bup_main module');
