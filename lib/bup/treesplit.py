"""
Tree-splitting algorithm.

Implement the tree-splitting algorithm, see also the description
in the DESIGN notes.
"""
from __future__ import absolute_import

from bup import git, _helpers
from bup.hashsplit import GIT_MODE_TREE, GIT_MODE_FILE


def _tree_names_abbreviate(names):
    abbrev = {}
    # build a trie (using dicts) out of all the names
    for name in names:
        level = abbrev
        for c in name:
            if not c in level:
                # use None as the back-pointer, not a valid char
                # (fun for the GC to detect the cycles :-) )
                level[c] = {None: level}
            level = level[c]
    outnames = []
    # and abbreviate all the names
    for name in names:
        out = name
        level = abbrev
        for n in range(len(name)):
            level = level[name[n]]
        while True:
            # backtrack a level
            level = level[None]
            # if it has more than a single char & None,
            # we cannot abbreviate any further
            if len(level) > 2:
                break
            candidate = out[:-1]
            # of course we must not have an invalid name
            if candidate in (b'', b'.', b'..'):
                break;
            out = candidate
        outnames.append(out)
    return outnames


def _tree_shalist_abbreviate(shalist):
    modes = [mode for mode, _, _ in shalist]
    names = [name for _, name, _ in shalist]
    sha1s = [sha1 for _, _, sha1 in shalist]
    outnames = _tree_names_abbreviate(names)
    return zip(modes, outnames, sha1s)


def _split_tree(new_tree, new_blob, shalist, level):
    outlist = []
    h = _helpers.RecordHashSplitter()
    treedata = []
    firstname = None
    for idx in range(len(shalist)):
        if firstname is None:
            firstname = shalist[idx][1]
        record = git.tree_encode([shalist[idx]])
        treedata.append(record)
        split, bits = h.feed(record)
        if split or idx == len(shalist) - 1:
            all_in_one_tree = not outlist and idx == len(shalist) - 1
            if all_in_one_tree and level > 0:
                # insert the sentinel file (empty blob)
                sentinel_sha = new_blob(b'')
                shalist.append((GIT_MODE_FILE, b'%d.bupd' % level, sentinel_sha))
                shalist.sort(key=git.shalist_item_sort_key)
                treedata = [git.tree_encode(shalist)]
            treeid = new_tree(content=b''.join(treedata))
            # if we've reached the end with an empty outlist,
            # just return this new tree (which is complete)
            if all_in_one_tree:
                return treeid
            outlist.append((GIT_MODE_TREE, firstname, treeid))
            # start over
            treedata = []
            firstname = None
    # If we have a real list, just subject it to tree-splitting
    # recursively. We use the (abbreviated) filename of the first
    # file in each next layer down so we can do more targeted
    # lookups when reading the data back.
    outlist = list(_tree_shalist_abbreviate(outlist))
    return _split_tree(new_tree, new_blob, outlist, level + 1)


def write_split_tree(new_tree, new_blob, shalist):
    shalist = sorted(shalist, key=git.shalist_item_sort_key)
    return _split_tree(new_tree, new_blob, shalist, 0)
