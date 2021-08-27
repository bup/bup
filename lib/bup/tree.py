
from __future__ import absolute_import, print_function


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

    def append(self, name, mode, gitmode, oid, meta):
        self.items.append(TreeItem(name, mode, gitmode, oid, meta))
