
from binascii import hexlify
import re

from bup import client, git
from bup.repo.base import _make_base, RepoProtocol


_oidx_rx = re.compile(br'[0-9a-fA-F]{40}')

class RemoteRepo(RepoProtocol):
    def __init__(self, location, create=False, compression_level=None,
                 max_pack_size=None, max_pack_objects=None):
        # The location must be a URL or a client.Config, and Client()
        # handles the validation.
        self._location = location
        self.closed = True # in case Client instantiation fails
        self.client = client.Client(location, create=create)
        self.closed = False
        self.config_get = self.client.config_get
        self._base = _make_base(self.config_get, compression_level,
                                max_pack_size, max_pack_objects)
        self.write_symlink = self.write_data
        self.write_bupm = self.write_data
        self.rev_list = self.client.rev_list
        self.list_indexes = self.client.list_indexes
        self.read_ref = self.client.read_ref
        self.send_index = self.client.send_index
        self.join = self.client.join
        self.refs = self.client.refs
        self.resolve = self.client.resolve
        self._packwriter = None

    def __repr__(self):
        cls = self.__class__
        return f'<{cls.__module__}.{cls.__name__} object at {hex(id(self))}' \
            f' location={self._location!r}>'

    def close(self):
        if not self.closed:
            self.closed = True
            self.finish_writing()
            if self.client:
                self.client.close()
                self.client = None

    def __del__(self): assert self.closed
    def __enter__(self): return self
    def __exit__(self, type, value, traceback): self.close()

    def update_ref(self, refname, newval, oldval):
        self.finish_writing()
        return self.client.update_ref(refname, newval, oldval)

    def _ensure_packwriter(self):
        if not self._packwriter:
            self._packwriter = self.client.new_packwriter(
                                    compression_level=self._base.compression_level,
                                    max_pack_size=self._base.max_pack_size,
                                    max_pack_objects=self._base.max_pack_objects)

    def is_remote(self): return True

    def cat(self, ref):
        # The data iterator must be consumed before any other client
        # interactions.  If the ref is 40 hex digits, then assume it's
        # an oid, and verify that the data provided by the remote
        # actually has that oid.  If not, throw.
        def hash_checked_data(kind, size, it, expected, batch):
            actual_oid = git.start_sha1(kind, size)
            for data in it:
                actual_oid.update(data)
                yield data
            actual_oid = actual_oid.digest()
            if hexlify(actual_oid) != expected:
                raise Exception(f'received {actual_oid.hex()}, expected oid {expected}')
            # causes client to finish the call
            assert not next(batch, None)

        batch = self.client.cat_batch((ref,))
        oidx, typ, size, it = items = next(batch, None) # cannot return None
        if not oidx:
            return items
        if not _oidx_rx.fullmatch(ref):
            return items
        return *items[:-1], hash_checked_data(typ, size, it, ref, batch)

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

    def just_write(self, oid, type, content):
        self._ensure_packwriter()
        return self._packwriter.just_write(oid, type, content)

    def exists(self, oid, want_source=False):
        self._ensure_packwriter()
        return self._packwriter.exists(oid, want_source=want_source)

    def finish_writing(self):
        if self._packwriter:
            w = self._packwriter
            self._packwriter = None
            return w.close()
        return None

    def abort_writing(self):
        if self._packwriter:
            self._packwriter.abort()
