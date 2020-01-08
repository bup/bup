
from __future__ import absolute_import
from importlib import import_module


class Kind:
    """
    Just declares the kinds of data you can store,
    use storage.Kind.DATA etc.
    """
    DATA, IDX, METADATA, CONFIG = range(4)

class StorageException(Exception):
    def __init__(self, name, message=None):
        self.name = name
        self.message = message or ""

class FileNotFound(StorageException):
    pass

class FileAlreadyExists(StorageException):
    pass

class FileModified(StorageException):
    pass

class BupStorage:
    def __init__(self, repo, create=False):
        """
        Initialize the storage for the given reponame, the storage backend
        can read its configuration using repo.config().
        """

    def __del__(self):
        self.close()

    def get_writer(self, name, kind, overwrite=None):
        """
        Return a writer object, i.e. an object that should have (at least)
        .write(data), .close() and .abort() methods.
        This may differentiate the kind of data to store based on the
        'kind' parameter, e.g. to store things in different places, different
        storage tiers in cloud storage, or such.
        If overwrite is not None, it must be an object obtained from the
        get_reader() method to atomically replace the file referenced by
        the reader. If it was modified since reading, raise FileModified().
        Note that this MUST raise FileAlreadyExists() if it already exists
        (unless overwriting.)
        """

    def get_reader(self, name, kind):
        """
        Return a reader object, i.e. an object that should have (at least)
        .read(size), .seek(absolute_offset) and .close() methods.
        For kind == Kind.CONFIG, the resulting object can be passed to the
        overwrite parameter of get_writer() to atomically replace the file.
        Raise FileNotFound(name) (with an optional message) if the file
        cannot be found.
        """

    def list(self, pattern=None):
        """
        Return an iterator/iterable over the list of filenames, globbed with
        the given fnmatch pattern (if any).
        """
        return
        # but have an empty 'yield' so the function is an iterator
        yield

    def close(self):
        """
        Close the storage (e.g. connection).
        """
        pass

def get_storage(repo, create=False):
    storage_name = repo.config(b'bup.storage').decode('ascii')
    if storage_name is None:
        raise Exception("Please specify storage for repository!")

    assert not '..' in storage_name

    try:
        module = import_module('bup.storage.%s' % storage_name.lower())
        clsname = storage_name + 'Storage'
        cls = getattr(module, clsname, None)
        if cls is None:
            raise Exception("Invalid storage '%s'" % storage_name)

        return cls(repo, create=create)
    except ImportError:
        raise Exception("Invalid storage '%s'" % storage_name)
