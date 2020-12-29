
def notimplemented(fn):
    def newfn(obj, *args, **kwargs):
        raise NotImplementedError(f'{obj.__class__.__name__}.{fn.__name__}')
    return newfn

class RepoProtocol:
    # Specification only; intentially has no implementations
    # Subclassing just indicates intent.
    # Currently, the vfs relies on id(repo) for caching paths.

    def _validate_init(self):
        """Ensures instance is sound; should be called by all subclasses."""
        hasattr(self, 'compression_level')
        hasattr(self, 'max_pack_objects')
        hasattr(self, 'max_pack_size')

    @notimplemented
    def is_remote(self):
        """Return true if this is a "remote" repository."""

    @notimplemented
    def join(self, ref):
        """..."""

    @notimplemented
    def resolve(self, path, parent=None, want_meta=True, follow=True):
        """..."""

    @notimplemented
    def config_get(self, name, opttype=None):
        """
        Return the configuration value of 'name', returning None if it doesn't
        exist. opttype indicates the type of option.
        """

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
    def write_commit(self, tree, parent,
                     author, adate_sec, adate_tz,
                     committer, cdate_sec, cdate_tz,
                     msg):
        """
        Tentatively write a new commit with the given parameters. You may use
        git.create_commit_blob().
        """

    @notimplemented
    def write_tree(self, shalist):
        """
        Tentatively write a new tree object into the repository, given the
        shalist (a list or tuple of (mode, name, oid)). You can use the
        git.tree_encode() function to convert from shalist to raw format.
        Return the new object's oid.
        """

    @notimplemented
    def write_data(self, data):
        """
        Tentatively write the given data into the repository.
        Return the new object's oid.
        """

    @notimplemented
    def write_symlink(self, target):
        """
        Tentatively write the given symlink target into the repository.
        Return the new object's oid.
        """

    @notimplemented
    def write_bupm(self, data):
        """
        Tentatively write the given bupm (fragment) into the repository.
        Return the new object's oid.
        """

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
