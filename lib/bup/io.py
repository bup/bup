
from __future__ import absolute_import, print_function

from bup import compat


if compat.py_maj > 2:
    def byte_stream(file):
        return file.buffer
else:
    def byte_stream(file):
        return file


def path_msg(x):
    """Return a string representation of a path."""
    # FIXME: configurability (might git-config quotePath be involved?)
    return x.decode(errors='backslashreplace')
