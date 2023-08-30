
# pylint: disable=unused-import
from contextlib import ExitStack, nullcontext
from os import environb as environ
from os import fsdecode, fsencode
from shlex import quote
import os, sys

def hexstr(b):
    """Return hex string (not bytes as with hexlify) representation of b."""
    return b.hex()

def reraise(ex):
    raise ex.with_traceback(sys.exc_info()[2])

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

byte_int = lambda x: x

def buffer(object, offset=None, size=None):
    if size:
        assert offset is not None
        return memoryview(object)[offset:offset + size]
    if offset:
        return memoryview(object)[offset:]
    return memoryview(object)

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

def wrap_main(main):
    """Run main() and raise a SystemExit with the return value if it
    returns, pass along any SystemExit it raises, convert
    KeyboardInterrupts into exit(130), and print a Python 3 style
    contextual backtrace for other exceptions in both Python 2 and
    3)."""
    try:
        sys.exit(main())
    except KeyboardInterrupt as ex:
        sys.exit(130)
