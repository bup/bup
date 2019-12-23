from wvpytest import *

from bup import tree


def test_abbreviate():
    l1 = [b'1234', b'1235', b'1236']
    WVPASSEQ(tree._abbreviate_tree_names(l1), l1)
    l2 = [b'aaaa', b'bbbb', b'cccc']
    WVPASSEQ(tree._abbreviate_tree_names(l2), [b'a', b'b', b'c'])
    l3 = [b'.bupm']
    WVPASSEQ(tree._abbreviate_tree_names(l3), [b'.b'])
    l4 = [b'..strange..name']
    WVPASSEQ(tree._abbreviate_tree_names(l4), [b'..s'])
    l5 = [b'justone']
    WVPASSEQ(tree._abbreviate_tree_names(l5), [b'j'])
