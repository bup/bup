
from __future__ import absolute_import

from bup.repo.base import BaseRepo
from bup import client


class RemoteRepo(BaseRepo):
    def __init__(self, address, create=False):
        super(RemoteRepo, self).__init__(address)
        # if client.Client() raises an exception, have a client
        # anyway to avoid follow-up exceptions from __del__
        self.client = None
        self.client = client.Client(address)
        self.rev_list = self.client.rev_list
        self.config = self.client.config
        self.list_indexes = self.client.list_indexes
        self.read_ref = self.client.read_ref
        self.send_index = self.client.send_index
        self.join = self.client.join
        self.refs = self.client.refs
        self.resolve = self.client.resolve
        self._packwriter = None

    def close(self):
        super(RemoteRepo, self).close()
        if self.client:
            self.client.close()
            self.client = None

    def update_ref(self, refname, newval, oldval):
        self.finish_writing()
        return self.client.update_ref(refname, newval, oldval)

    def _ensure_packwriter(self):
        if not self._packwriter:
            self._packwriter = self.client.new_packwriter()

    def is_remote(self):
        return True

    def cat(self, ref):
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

    def write_tree(self, shalist=None, content=None):
        self._ensure_packwriter()
        return self._packwriter.new_tree(shalist=shalist, content=content)

    def write_data(self, data):
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

    def abort_writing(self):
        if self._packwriter:
            self._packwriter.abort()
