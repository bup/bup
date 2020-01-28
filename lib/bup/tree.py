
from __future__ import absolute_import, print_function

from io import BytesIO

from bup.hashsplit import GIT_MODE_TREE
from bup.hashsplit import split_to_blob_or_tree
from bup.helpers import add_error
from bup.io import path_msg
from bup.git import shalist_item_sort_key, mangle_name


def _write_tree(w, dir_meta, items):
    metalist = [(b'', dir_meta)]
    metalist += [(shalist_item_sort_key((entry.mode, entry.name, None)),
                  entry.meta)
                 for entry in items if entry.mode != GIT_MODE_TREE]
    metalist.sort(key = lambda x: x[0])
    metadata = BytesIO(b''.join(m[1].encode() for m in metalist))
    mode, oid = split_to_blob_or_tree(w.new_blob, w.new_tree,
                                     [metadata],
                                     keep_boundaries=False)
    shalist = [(mode, b'.bupm', oid)]
    shalist += [(entry.gitmode,
                 mangle_name(entry.name, entry.mode, entry.gitmode),
                 entry.oid)
                for entry in items]
    return w.new_tree(shalist)

class TreeItem:
    __slots__ = 'name', 'mode', 'gitmode', 'oid', 'meta'

    def __init__(self, name, mode, gitmode, oid, meta):
        self.name = name
        self.mode = mode
        self.gitmode = gitmode
        self.oid = oid
        self.meta = meta

class StackDir:
    __slots__ = 'name', 'items', 'meta'

    def __init__(self, name, meta):
        self.name = name
        self.meta = meta
        self.items = []

class Stack:
    def __init__(self):
        self.stack = []

    def __len__(self):
        return len(self.stack)

    def path(self):
        return [p.name for p in self.stack]

    def push(self, name, meta):
        self.stack.append(StackDir(name, meta))

    def _clean(self, tree):
        names_seen = set()
        items = []
        for item in tree.items:
            if item.name in names_seen:
                parent_path = b'/'.join(n for n in self.path()) + b'/'
                add_error('error: ignoring duplicate path %s in %s'
                          % (path_msg(item.name), path_msg(parent_path)))
            else:
                names_seen.add(item.name)
                items.append(item)
        return items

    def _write(self, w, tree):
        return _write_tree(w, tree.meta, self._clean(tree))

    def pop(self, w, override_tree=None, override_meta=None):
        tree = self.stack.pop()
        if override_meta is not None:
            tree.meta = override_meta
        if not override_tree: # caution - False happens, not just None
            tree_oid = self._write(w, tree)
        else:
            tree_oid = override_tree
        if len(self):
            self.append_to_current(tree.name, GIT_MODE_TREE, GIT_MODE_TREE,
                                   tree_oid, None)
        return tree_oid

    def append_to_current(self, name, mode, gitmode, oid, meta):
        self.stack[-1].items.append(TreeItem(name, mode, gitmode, oid, meta))
