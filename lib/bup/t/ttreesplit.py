
from __future__ import absolute_import
from io import BytesIO

from wvtest import *

from bup import treesplit
from buptest import no_lingering_errors


@wvtest
def test_abbreviate():
    with no_lingering_errors():
        l1 = [b"1234", b"1235", b"1236"]
        WVPASSEQ(treesplit._tree_names_abbreviate(l1), l1)
        l2 = [b"aaaa", b"bbbb", b"cccc"]
        WVPASSEQ(treesplit._tree_names_abbreviate(l2), [b'a', b'b', b'c'])
        l3 = [b".bupm"]
        WVPASSEQ(treesplit._tree_names_abbreviate(l3), [b'.b'])
        l4 = [b"..strange..name"]
        WVPASSEQ(treesplit._tree_names_abbreviate(l4), [b'..s'])
        l5 = [b"justone"]
        WVPASSEQ(treesplit._tree_names_abbreviate(l5), [b'j'])
