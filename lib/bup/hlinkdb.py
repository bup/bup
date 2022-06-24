
from contextlib import ExitStack
import os, pickle

from bup.helpers import atomically_replaced_file, unlink


def pickle_load(filename):
    try:
        f = open(filename, 'rb')
    except FileNotFoundError:
        return None
    with f:
        return pickle.load(f, encoding='bytes')


class Error(Exception):
    pass

class HLinkDB:
    def __init__(self, filename):
        self.closed = False
        self._cleanup = ExitStack()
        self._filename = filename
        self._pending_save = None
        # Map a "dev:ino" node to a list of paths associated with that node.
        self._node_paths = pickle_load(filename) or {}
        # Map a path to a "dev:ino" node (a reverse hard link index).
        self._path_node = {}
        for node, paths in self._node_paths.items():
            for path in paths:
                self._path_node[path] = node

    def prepare_save(self):
        """ Commit all of the relevant data to disk.  Do as much work
        as possible without actually making the changes visible."""
        if self._pending_save:
            raise Error('save of %r already in progress' % self._filename)
        with self._cleanup:
            if self._node_paths:
                dir, name = os.path.split(self._filename)
                self._pending_save = atomically_replaced_file(self._filename,
                                                              mode='wb',
                                                              buffering=65536)
                with self._cleanup.enter_context(self._pending_save) as f:
                    pickle.dump(self._node_paths, f, 2)
            else: # No data
                self._cleanup.callback(lambda: unlink(self._filename))
            self._cleanup = self._cleanup.pop_all()

    def commit_save(self):
        self.closed = True
        if self._node_paths and not self._pending_save:
            raise Error('cannot commit save of %r; no save prepared'
                        % self._filename)
        self._cleanup.close()
        self._pending_save = None

    def abort_save(self):
        self.closed = True
        with self._cleanup:
            if self._pending_save:
                self._pending_save.cancel()
        self._pending_save = None

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.abort_save()

    def __del__(self):
        assert self.closed

    def add_path(self, path, dev, ino):
        # Assume path is new.
        node = b'%d:%d' % (dev, ino)
        self._path_node[path] = node
        link_paths = self._node_paths.get(node)
        if link_paths and path not in link_paths:
            link_paths.append(path)
        else:
            self._node_paths[node] = [path]

    def _del_node_path(self, node, path):
        link_paths = self._node_paths[node]
        link_paths.remove(path)
        if not link_paths:
            del self._node_paths[node]

    def change_path(self, path, new_dev, new_ino):
        prev_node = self._path_node.get(path)
        if prev_node:
            self._del_node_path(prev_node, path)
        self.add_path(new_dev, new_ino, path)

    def del_path(self, path):
        # Path may not be in db (if updating a pre-hardlink support index).
        node = self._path_node.get(path)
        if node:
            self._del_node_path(node, path)
            del self._path_node[path]

    def node_paths(self, dev, ino):
        node = b'%d:%d' % (dev, ino)
        return self._node_paths[node]
