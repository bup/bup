
from __future__ import absolute_import, print_function
import os
import struct
from contextlib import contextmanager

import hashlib

from wvtest import *

from buptest import no_lingering_errors, test_tempdir
from bup.storage import Kind, FileAlreadyExists, FileNotFound, get_storage
from bup import git


try:
    # Allow testing this against any kind of storage backend
    # (for development) - note that you may have to clean up
    # data inside it after each run manually.
    repo_conf = os.environ['STORAGE_TEST_CONF']
except KeyError:
    repo_conf = None

@contextmanager
def create_test_config():
    with test_tempdir('enc') as tmpdir:
        if repo_conf is None:
            cfgfile = os.path.join(tmpdir, 'repo.conf')
            cfg = open(cfgfile, 'wb')
            cfg.write(b'[bup]\n')
            cfg.write(b'  storage = File\n')
            cfg.write(b'  path = %s\n' % os.path.join(tmpdir, 'repo'))
            cfg.write(b'  cachedir = %s\n' % os.path.join(tmpdir, 'cache'))
            cfg.close()
            create = True
        else:
            wvstart("storage config from %s" % repo_conf)
            cfgfile = repo_conf
            create = False
        class FakeRepo:
            def config(self, k, opttype=None, default=None):
                assert isinstance(k, bytes)
                return git.git_config_get(k, cfg_file=cfgfile,
                                          opttype=opttype,
                                          default=default)
        store = get_storage(FakeRepo(), create=create)
        yield tmpdir, store
        del store

@wvtest
def test_storage_config():
    with no_lingering_errors(), create_test_config() as (tmpdir, store):
        wvstart("create a new file")
        wr = store.get_writer('test-storage-overwrite', Kind.CONFIG)
        wr.write(b'a' * 100)
        wr.close()

        wvstart("cannot overwrite it")
        wvexcept(FileAlreadyExists, store.get_writer,
                 'test-storage-overwrite', Kind.CONFIG)

        wvstart("replace it atomically")
        rd = store.get_reader('test-storage-overwrite', Kind.CONFIG)
        wr = store.get_writer('test-storage-overwrite', Kind.CONFIG,
                              overwrite=rd)
        wr.write(b'b' * 100)
        wr.close()
        wr = store.get_writer('test-storage-overwrite', Kind.CONFIG,
                              overwrite=rd)
        wr.write(b'c' * 100)
        wr.abort()
        wvpasseq(rd.read(), b'a' * 100)
        rd.close()

        rd = store.get_reader('test-storage-overwrite', Kind.CONFIG)
        wvpasseq(rd.read(), b'b' * 100)
        wvstart("seek")
        wvpasseq(rd.read(), b'')
        rd.seek(0)
        wvpasseq(rd.read(), b'b' * 100)
        rd.seek(90)
        wvpasseq(rd.read(), b'b' * 10)
        rd.close()

        wvstart("not found")
        wvexcept(FileNotFound, store.get_reader, 'test-404', Kind.CONFIG)

@wvtest
def test_storage_packs():
    with no_lingering_errors(), create_test_config() as (tmpdir, store):
        kinds = {
            Kind.METADATA: ("METADATA", "mpack"),
            Kind.DATA: ("DATA", "dpack"),
            Kind.IDX: ("IDX", "idx"),
        }
        for kind, (kindname, ext) in kinds.items():
            wvstart("create a new file %s" % kindname)
            filename = 'pack-zzzzzzz.%s' % ext
            wr = store.get_writer(filename, kind)
            wr.write(b'a' * 100)
            wr.close()

            for nkind, (nkindname, _) in kinds.items():
                wvstart("cannot overwrite by %s" % nkindname)
                wvexcept(FileAlreadyExists, store.get_writer,
                         filename, kind)
                rd = store.get_reader(filename, kind)
                wvexcept(Exception, store.get_writer,
                         filename, kind, overwrite=rd)
                rd.close()

            wvstart("read back")
            rd = store.get_reader(filename, kind)
            wvpasseq(rd.read(), b'a' * 100)
            rd.close()
