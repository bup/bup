
from __future__ import absolute_import
import tempfile
import os
import fnmatch
import hashlib
import fcntl
from functools import partial
from contextlib import contextmanager

from bup.storage import BupStorage, FileAlreadyExists, FileNotFound, Kind, FileModified
from bup.helpers import mkdirp
from bup.io import path_msg


UMASK = os.umask(0)
os.umask(UMASK)

def _hash_f(f):
    sha = hashlib.sha1()
    for chunk in iter(partial(f.read, 1024 * 1024), b''):
        sha.update(chunk)
    f.seek(0)
    return sha.digest()


class FileWriter:
    def __init__(self, path, filename, overwrite, openset):
        self.f = None
        self.filename = os.path.join(path, filename)
        self.overwrite = overwrite
        if overwrite:
            assert isinstance(overwrite, FileReader)
            assert overwrite.kind == Kind.CONFIG
            assert overwrite.f is not None
            # create if it didn't exist yet
            self.lockpath = os.path.join(path, b'repolock')
            open(self.lockpath, 'a')
        elif os.path.exists(self.filename):
            raise FileAlreadyExists(filename)
        fd, self.tmp_filename = tempfile.mkstemp(prefix=b'_tmp_', dir=path)
        self.f = os.fdopen(fd, 'wb')
        self.openset = openset
        self.openset.add(self)

    def __del__(self):
        if self.f:
            self.abort()

    def write(self, data):
        assert self.f is not None
        self.f.write(data)

    @contextmanager
    def _locked(self):
        fd = os.open(self.lockpath, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def close(self):
        assert self.f is not None
        self.openset.remove(self)
        self.f.close()
        self.f = None
        if self.overwrite:
            with self._locked():
                hash = _hash_f(open(self.filename, 'rb'))
                if hash != self.overwrite.hash:
                    raise FileModified(self.filename)
                os.chmod(self.tmp_filename, 0o666 & ~UMASK)
                os.rename(self.tmp_filename, self.filename)
        else:
            os.chmod(self.tmp_filename, 0o666 & ~UMASK)
            os.rename(self.tmp_filename, self.filename)

    def abort(self):
        assert self.f is not None
        self.openset.remove(self)
        self.f.close()
        self.f = None
        os.unlink(self.tmp_filename)

class FileReader:
    def __init__(self, path, filename, kind, openset):
        self.f = None
        self.filename = os.path.join(path, filename)
        if not os.path.exists(self.filename):
            raise FileNotFound(filename)
        self.f = open(self.filename, 'rb')
        self.openset = openset
        self.openset.add(self)
        self.kind = kind
        if kind == Kind.CONFIG:
            self.hash = _hash_f(self.f)

    def __del__(self):
        if self.f:
            self.close()

    def read(self, sz=None):
        assert self.f is not None
        if sz is None:
            pos = self.f.tell()
            self.f.seek(0, 2)
            sz = self.f.tell()
            self.f.seek(pos)
        return self.f.read(sz)

    def close(self):
        assert self.f is not None
        self.openset.remove(self)
        self.f.close()
        self.f = None

    def seek(self, offs):
        assert self.f is not None
        self.f.seek(offs)

class FileStorage(BupStorage):
    def __init__(self, repo, create=False):
        self.openset = set()
        self.path = repo.config(b'bup.path')
        if create:
            mkdirp(self.path)
        if not os.path.isdir(self.path):
            raise Exception("FileStorage: %s doesn't exist or isn't a directory, need to init?" % path_msg(self.path))

    def __del__(self):
        self.close()

    # we wrap open() here to ensure it doesn't exist yet
    # and that we write to a temporary file first
    def get_writer(self, name, kind, overwrite=None):
        assert kind in (Kind.DATA, Kind.METADATA, Kind.IDX, Kind.CONFIG)
        return FileWriter(self.path, name, overwrite, self.openset)

    # we wrap open() here to ensure only our limited API is available
    def get_reader(self, name, kind):
        return FileReader(self.path, name, kind, self.openset)

    def list(self, pattern=None):
        # be an iterator here for test purposes, rather than
        # returning the list, to ensure nothing relies on this
        # being a list ...
        for n in fnmatch.filter(os.listdir(self.path), pattern or '*'):
            yield n

    def close(self):
        assert not self.openset, self.openset
