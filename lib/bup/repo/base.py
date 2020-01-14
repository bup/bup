
from __future__ import absolute_import

from bup import vfs


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

def notimplemented(fn):
    def newfn(obj, *args, **kwargs):
        raise NotImplementedError("%s::%s must be implemented" % (
                                    obj.__class__.__name__, fn.__name__))
    return newfn

class BaseRepo(object):
    def __init__(self, key):
        self._id = _repo_id(key)

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def close(self):
        self.finish_writing()

    def id(self):
        """Return an identifier that differs from any other repository that
        doesn't share the same repository-specific information
        (e.g. refs, tags, etc.)."""
        return self._id

    @property
    def dumb_server_mode(self):
        return False

    def is_remote(self):
        return False

    def join(self, ref):
        return vfs.join(self, ref)

    def resolve(self, path, parent=None, want_meta=True, follow=True):
        ## FIXME: mode_only=?
        return vfs.resolve(self, path, parent=parent,
                           want_meta=want_meta, follow=follow)

    @notimplemented
    def list_indexes(self):
        """
        List all indexes in this repository (optional, used only by bup server)
        """

    @notimplemented
    def read_ref(self, refname):
        """
        Read the ref called 'refname', return the oidx (hex oid)
        """

    @notimplemented
    def update_ref(self, refname, newval, oldval):
        """
        Update the ref called 'refname' from oldval (None if it previously
        didn't exist) to newval, atomically doing a check against oldval
        and updating to newval. Both oldval and newval are given as oidx
        (hex-encoded oid).
        """

    @notimplemented
    def cat(self, ref):
        """
        If ref does not exist, yield (None, None, None).  Otherwise yield
        (oidx, type, size), and then all of the data associated with ref.
        """

    @notimplemented
    def refs(self, patterns=None, limit_to_heads=False, limit_to_tags=False):
        """
        Yield the refs filtered according to the list of patterns,
        limit_to_heads ("refs/heads"), tags ("refs/tags/") or both.
        """

    @notimplemented
    def send_index(self, name, conn, send_size):
        """
        Read the given index (name), then call the send_size
        function with its size as the only argument, and write
        the index to the given conn using conn.write().
        (optional, used only by bup server)
        """

    @notimplemented
    def rev_list_raw(self, refs, count, fmt):
        """
        Yield chunks of data of the raw rev-list in git format.
        (optional, used only by bup server)
        """

    @notimplemented
    def write_commit(self, tree, parent,
                     author, adate_sec, adate_tz,
                     committer, cdate_sec, cdate_tz,
                     msg):
        """
        Tentatively write a new commit with the given parameters. You may use
        git.create_commit_blob().
        """

    @notimplemented
    def write_tree(self, shalist=None, content=None):
        """
        Tentatively write a new tree object into the repository, given either
        the shalist (a list or tuple of (mode, name, oid)) or the content
        (already formatted in git tree blob format). You can use the
        git.tree_encode() function to convert from shalist to raw format.
        Return the new object's oid.
        """

    @notimplemented
    def write_data(self, data):
        """
        Tentatively write the given data into the repository.
        Return the new object's oid.
        """

    def write_symlink(self, target):
        """
        Tentatively write the given symlink target into the repository.
        Return the new object's oid.
        """
        return self.write_data(target)

    def write_bupm(self, data):
        """
        Tentatively write the given bupm (fragment) into the repository.
        Return the new object's oid.
        """
        return self.write_data(data)

    @notimplemented
    def just_write(self, oid, type, content):
        """
        TODO
        """

    @notimplemented
    def finish_writing(self, run_midx=True):
        """
        Finish writing, i.e. really add the previously tentatively written
        objects to the repository.
        TODO: document run_midx
        """

    @notimplemented
    def abort_writing(self):
        """
        Abort writing and delete all the previously tenatively written objects.
        """

    @notimplemented
    def exists(self, oid, want_source=False):
        """
        Check if the given oid (binary format) already exists in the
        repository (or the tentatively written objects), returning
        None if not, True if it exists, or the idx name if want_source
        is True and it exists.
        """
