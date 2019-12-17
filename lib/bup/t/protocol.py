
from __future__ import absolute_import, print_function
from io import BytesIO

from wvtest import *

from bup import git, metadata, vfs, protocol
from buptest import no_lingering_errors


@wvtest
def test_item_read_write():
    with no_lingering_errors():
        x = vfs.Root(meta=13)
        stream = BytesIO()
        protocol.write_item(stream, x)
        print('stream:', repr(stream.getvalue()), stream.tell(), file=sys.stderr)
        stream.seek(0)
        wvpasseq(x, protocol.read_item(stream))
