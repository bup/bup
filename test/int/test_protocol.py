
from io import BytesIO
import sys

from wvpytest import *

from bup import vfs, protocol


def test_item_read_write():
    x = vfs.Root(meta=13)
    stream = BytesIO()
    protocol.write_item(stream, x)
    print('stream:', repr(stream.getvalue()), stream.tell(), file=sys.stderr)
    stream.seek(0)
    wvpasseq(x, protocol.read_item(stream))
