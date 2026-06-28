
# Until min pylint is new enough for disable-next
# pylint: disable=unused-import
# pylint: disable-next=unused-import
from os import environb as environ
# pylint: enable=unused-import
from os import fsencode
import dataclasses, sys, traceback


ver = sys.version_info

if (ver.major, ver.minor) >= (3, 10):
    # pylint: disable=unused-import
    # pylint: disable-next=unused-import
    from itertools import pairwise
    # pylint: enable=unused-import
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

# Access argv directly, given https://bugs.python.org/issue35883

def get_argvb():
    "Return a new list containing the current process argv bytes."
    return [fsencode(x) for x in sys.argv]

def get_argv():
    "Return a new list containing the current process argv strings."
    return list(sys.argv)

# Makes slots best effort
if (ver.major, ver.minor) >= (3, 10):
    dataclass = dataclasses.dataclass
else:
    def dataclass(*args, **kwargs):
        del kwargs['slots']
        return dataclasses.dataclass(*args, **kwargs)

# "frozen for testing" is handled as a separate decorator because if
# it's handled dynamically, say as a bespoke frozen setting like
# frozen='testing' for our dataclass above, pylint (st least 3.3.4)
# gets confused and starts issuing false positives for no-member in
# some cases (e.g. field() fields).
#
# We have this because because while the docs claim there is only "a
# tiny performance penalty" for frozen=True[1], it's currently
# expensive.  Try "drecurse | pv -l > /dev/null" on a large tree with
# and without a frozen stat_result, with a warm cache.
#
# [1] https://docs.python.org/3/library/dataclasses.html#frozen-instances

if b'BUP_TEST_LEVEL' not in environ:
    # So pylint can still understand it as a dataclasses.dataclass
    dataclass_frozen_for_testing = dataclass
else:
    def dataclass_frozen_for_testing(*args, **kwargs):
        """Exactly like dataclasses.dataclass except that frozen=True."""
        assert 'frozen' not in kwargs, kwargs
        kwargs['frozen'] = True
        return dataclass(*args, **kwargs)
