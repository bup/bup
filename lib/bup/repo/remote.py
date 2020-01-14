
from bup.repo.base import BaseRepo
from bup import client
from bup.compat import pending_raise


class RemoteRepo(BaseRepo):
    def __init__(self, address, create=False, compression_level=None,
                 max_pack_size=None, max_pack_objects=None):
        super(RemoteRepo, self).__init__(address,
                                         compression_level=compression_level,
                                         max_pack_size=max_pack_size,
                                         max_pack_objects=max_pack_objects)
        self.closed = True # in case Client instantiation fails
        self.client = client.Client(address, create=create)
        self.closed = False
        self.rev_list = self.client.rev_list
        self.config_get = self.client.config_get
        self.list_indexes = self.client.list_indexes
        self.read_ref = self.client.read_ref
        self.send_index = self.client.send_index
        self.join = self.client.join
        self.refs = self.client.refs
        self.resolve = self.client.resolve
        self._packwriter = None

    def close(self):
        self.finish_writing()
        if not self.closed:
            self.closed = True
            self.finish_writing()
            self.client.close()
            self.client = None

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        with pending_raise(value, rethrow=False):
            self.close()

    def update_ref(self, refname, newval, oldval):
        self.finish_writing()
        return self.client.update_ref(refname, newval, oldval)

    def _ensure_packwriter(self):
        if not self._packwriter:
            self._packwriter = self.client.new_packwriter(
                                    compression_level=self.compression_level,
                                    max_pack_size=self.max_pack_size,
                                    max_pack_objects=self.max_pack_objects)

    def is_remote(self):
        return True

    def cat(self, ref):
        """If ref does not exist, yield (None, None, None).  Otherwise yield
        (oidx, type, size), and then all of the data associated with
        ref.

        """
        # Yield all the data here so that we don't finish the
        # cat_batch iterator (triggering its cleanup) until all of the
        # data has been read.  Otherwise we'd be out of sync with the
        # server.
        items = self.client.cat_batch((ref,))
        oidx, typ, size, it = info = next(items)
        yield info[:-1]
        if oidx:
            for data in it:
                yield data
        assert not next(items, None)

    def write_commit(self, tree, parent,
                     author, adate_sec, adate_tz,
                     committer, cdate_sec, cdate_tz,
                     msg):
        self._ensure_packwriter()
        return self._packwriter.new_commit(tree, parent,
                                           author, adate_sec, adate_tz,
                                           committer, cdate_sec, cdate_tz,
                                           msg)

    def write_tree(self, shalist):
        self._ensure_packwriter()
        return self._packwriter.new_tree(shalist)

    def write_data(self, data):
        self._ensure_packwriter()
        return self._packwriter.new_blob(data)

    def write_symlink(self, target):
        self._ensure_packwriter()
        return self._packwriter.new_blob(target)

    def write_bupm(self, data):
        self._ensure_packwriter()
        return self._packwriter.new_blob(data)

    def just_write(self, sha, type, content):
        self._ensure_packwriter()
        return self._packwriter.just_write(sha, type, content)

    def exists(self, sha, want_source=False):
        self._ensure_packwriter()
        return self._packwriter.exists(sha, want_source=want_source)

    def finish_writing(self, run_midx=True):
        if self._packwriter:
            w = self._packwriter
            self._packwriter = None
            return w.close()
        return None

    def abort_writing(self):
        if self._packwriter:
            self._packwriter.abort()
