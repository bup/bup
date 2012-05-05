import cPickle, errno, os, tempfile

class Error(Exception):
    pass

class HLinkDB:
    def __init__(self, filename):
        # Map a "dev:ino" node to a list of paths associated with that node.
        self._node_paths = {}
        # Map a path to a "dev:ino" node.
        self._path_node = {}
        self._filename = filename
        self._save_prepared = None
        self._tmpname = None
        f = None
        try:
            f = open(filename, 'r')
        except IOError, e:
            if e.errno == errno.ENOENT:
                pass
            else:
                raise
        if f:
            try:
                self._node_paths = cPickle.load(f)
            finally:
                f.close()
                f = None
        # Set up the reverse hard link index.
        for node, paths in self._node_paths.iteritems():
            for path in paths:
                self._path_node[path] = node

    def prepare_save(self):
        """ Commit all of the relevant data to disk.  Do as much work
        as possible without actually making the changes visible."""
        if self._save_prepared:
            raise Error('save of %r already in progress' % self._filename)
        if self._node_paths:
            (dir, name) = os.path.split(self._filename)
            (ffd, self._tmpname) = tempfile.mkstemp('.tmp', name, dir)
            try:
                f = os.fdopen(ffd, 'wb', 65536)
            except:
                os.close(ffd)
                raise
            try:
                cPickle.dump(self._node_paths, f, 2)
            except:
                f.close()
                os.unlink(self._tmpname)
                self._tmpname = None
                raise
            else:
                f.close()
                f = None
        self._save_prepared = True

    def commit_save(self):
        if not self._save_prepared:
            raise Error('cannot commit save of %r; no save prepared'
                        % self._filename)
        if self._tmpname:
            os.rename(self._tmpname, self._filename)
            self._tmpname = None
        else: # No data -- delete _filename if it exists.
            try:
                os.unlink(self._filename)
            except OSError, e:
                if e.errno == errno.ENOENT:
                    pass
                else:
                    raise
        self._save_prepared = None

    def abort_save(self):
        if self._tmpname:
            os.unlink(self._tmpname)
            self._tmpname = None

    def __del__(self):
        self.abort_save()

    def add_path(self, path, dev, ino):
        # Assume path is new.
        node = '%s:%s' % (dev, ino)
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
        node = '%s:%s' % (dev, ino)
        return self._node_paths[node]
