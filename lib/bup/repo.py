
from __future__ import absolute_import
import os, subprocess
from os.path import realpath
from functools import partial

from bup import client, git, vfs


_next_repo_id = 0
_repo_ids = {}

def _repo_id(key):
    global _next_repo_id, _repo_ids
    repo_id = _repo_ids.get(key)
    if repo_id:
        return repo_id
    next_id = _next_repo_id = _next_repo_id + 1
    _repo_ids[key] = next_id
    return next_id

class LocalRepo:
    def __init__(self, repo_dir=None, compression_level=1,
                 max_pack_size=None, max_pack_objects=None,
                 objcache_maker=None):
        self.repo_dir = realpath(git.guess_repo(repo_dir))
        self._cp = git.cp(self.repo_dir)
        self.rev_list = partial(git.rev_list, repo_dir=self.repo_dir)
        self.config = partial(git.git_config_get, repo_dir=self.repo_dir)
        self._id = _repo_id(self.repo_dir)
        self._dumb_server_mode = None
        self._packwriter = None
        self.compression_level = compression_level
        self.max_pack_size = max_pack_size
        self.max_pack_objects = max_pack_objects
        self.objcache_maker = objcache_maker

    @classmethod
    def create(self, repo_dir=None):
        # FIXME: this is not ideal, we should somehow
        # be able to call the constructor instead?
        git.init_repo(repo_dir)
        git.check_repo_or_die(repo_dir)

    def close(self):
        self.finish_writing()

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    @property
    def dumb_server_mode(self):
        if self._dumb_server_mode is None:
            self._dumb_server_mode = os.path.exists(git.repo(b'bup-dumb-server',
                                                             repo_dir=self.repo_dir))
        return self._dumb_server_mode

    def id(self):
        """Return an identifier that differs from any other repository that
        doesn't share the same repository-specific information
        (e.g. refs, tags, etc.)."""
        return self._id

    def is_remote(self):
        return False

    def list_indexes(self):
        for f in os.listdir(git.repo(b'objects/pack',
                                     repo_dir=self.repo_dir)):
            yield f

    def read_ref(self, refname):
        return git.read_ref(refname, repo_dir=self.repo_dir)

    def _ensure_packwriter(self):
        if not self._packwriter:
            self._packwriter = git.PackWriter(repo_dir=self.repo_dir,
                                              compression_level=self.compression_level,
                                              max_pack_size=self.max_pack_size,
                                              max_pack_objects=self.max_pack_objects,
                                              objcache_maker=self.objcache_maker)

    def update_ref(self, refname, newval, oldval):
        self.finish_writing()
        return git.update_ref(refname, newval, oldval, repo_dir=self.repo_dir)

    def cat(self, ref):
        """If ref does not exist, yield (None, None, None).  Otherwise yield
        (oidx, type, size), and then all of the data associated with
        ref.

        """
        it = self._cp.get(ref)
        oidx, typ, size = info = next(it)
        yield info
        if oidx:
            for data in it:
                yield data
        assert not next(it, None)

    def join(self, ref):
        return self._cp.join(ref)

    def refs(self, patterns=None, limit_to_heads=False, limit_to_tags=False):
        for ref in git.list_refs(patterns=patterns,
                                 limit_to_heads=limit_to_heads,
                                 limit_to_tags=limit_to_tags,
                                 repo_dir=self.repo_dir):
            yield ref

    ## Of course, the vfs better not call this...
    def resolve(self, path, parent=None, want_meta=True, follow=True):
        ## FIXME: mode_only=?
        return vfs.resolve(self, path,
                           parent=parent, want_meta=want_meta, follow=follow)

    def send_index(self, name, conn, send_size):
        data = git.open_idx(git.repo(b'objects/pack/%s' % name,
                                     repo_dir=self.repo_dir)).map
        send_size(len(data))
        conn.write(data)

    def rev_list_raw(self, refs, count, fmt):
        args = git.rev_list_invocation(refs, count=count, format=fmt)
        p = subprocess.Popen(args, env=git._gitenv(self.repo_dir),
                             stdout=subprocess.PIPE)
        while True:
            out = p.stdout.read(64 * 1024)
            if not out:
                break
            yield out
        rv = p.wait()  # not fatal
        if rv:
            raise git.GitError('git rev-list returned error %d' % rv)

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
            return w.close(run_midx=run_midx)

    def abort_writing(self):
        if self._packwriter:
            self._packwriter.abort()

def make_repo(address, create=False):
    return RemoteRepo(address, create=create)

class RemoteRepo:
    def __init__(self, address, create=False):
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
        self._id = _repo_id(address)
        self._packwriter = None

    def close(self):
        self.finish_writing()
        if self.client:
            self.client.close()
            self.client = None

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def id(self):
        """Return an identifier that differs from any other repository that
        doesn't share the same repository-specific information
        (e.g. refs, tags, etc.)."""
        return self._id

    def update_ref(self, refname, newval, oldval):
        self.finish_writing()
        return self.client.update_ref(refname, newval, oldval)

    def _ensure_packwriter(self):
        if not self._packwriter:
            self._packwriter = self.client.new_packwriter()

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

    def write_tree(self, shalist=None, content=None):
        self._ensure_packwriter()
        return self._packwriter.new_tree(shalist=shalist, content=content)

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

    def abort_writing(self):
        if self._packwriter:
            self._packwriter.abort()
