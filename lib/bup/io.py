
from __future__ import absolute_import, print_function

from bup import compat


if compat.py_maj > 2:
    def byte_stream(file):
        return file.buffer
else:
    def byte_stream(file):
        return file


def path_msg(x):
    """Return a string representation of a path.

    For now, assume that the destination encoding is going to be
    ISO-8859-1, which it should be, for the primary current
    destination, stderr, given the current bup-python.

    """
    # FIXME: configurability (might git-config quotePath be involved?)
    return x.decode(encoding='iso-8859-1')
