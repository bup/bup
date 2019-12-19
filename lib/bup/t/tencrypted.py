
from __future__ import absolute_import, print_function
import os
import struct
from contextlib import contextmanager

from wvtest import *

try:
    import libnacl
except ImportError:
    # TODO: is there a wvskip? or some exception?
    wvmsg("skipping, libnacl unavailable")
    def wvtest(fn):
        return None

from buptest import no_lingering_errors, test_tempdir
from bup import storage, git
from bup.storage import Kind
from bup.repo import ConfigRepo, encrypted


@contextmanager
def create_test_config():
    with test_tempdir(b'enc') as tmpdir:
        cfgfile = os.path.join(tmpdir, b'repo.conf')
        cfg = open(cfgfile, 'wb')
        cfg.write(b'[bup]\n')
        cfg.write(b'  storage = File\n')
        cfg.write(b'  path = %s\n' % os.path.join(tmpdir, b'repo'))
        cfg.write(b'  cachedir = %s\n' % os.path.join(tmpdir, b'cache'))
        cfg.close()
        yield tmpdir, storage.get_storage(ConfigRepo(cfg_file=cfgfile),
                                          create=True)

@wvtest
def test_encrypted_container():
    with no_lingering_errors(), create_test_config() as (tmpdir, store):
        secret = libnacl.public.SecretKey()

        p = encrypted.EncryptedContainer(store, b'test.pack', 'w', Kind.DATA,
                                         compression=9, key=secret.pk)
        p.finish()
        pfile = open(os.path.join(tmpdir, b'repo', b'test.pack'), 'rb')
        # minimum file size with header and footer
        wvpasseq(len(pfile.read()), 92)

        p = encrypted.EncryptedContainer(store, b'test2.pack', 'w', Kind.DATA,
                                         compression=9, key=secret.pk)
        offsets = {}
        offsets[b'A'] = p.write(3, None, b'A'* 1000)
        offsets[b'B'] = p.write(3, None, b'B'* 1000)
        offsets[b'C'] = p.write(3, None, b'C'* 1000)
        offsets[b'D'] = p.write(3, None, b'D'* 1000)
        offsets[b'ABCD'] = p.write(3, None, b'ABCD'* 250)
        sk = p.box.sk
        p.finish()
        pfile = open(os.path.join(tmpdir, b'repo', b'test2.pack'), 'rb')
        pdata = pfile.read()
        # the simple stuff above compresses well
        wvpasseq(len(pdata), 265)

        # check header
        wvpasseq(struct.unpack('<4sBBH', pdata[:8]), (b'BUPe', 1, 0, 84))

        # check secret header
        eh = libnacl.sealed.SealedBox(secret).decrypt(pdata[8:84 + 8])
        wvpasseq(struct.unpack('<BBBB', eh[:4]), (1, 1, 1, 1))
        # ignore vuint_key here, it's random
        wvpasseq(sk, eh[4:])

        # read the objects and check if they're fine
        p = encrypted.EncryptedContainer(store, b'test2.pack', 'r', Kind.DATA,
                                         key=secret)
        for k in sorted(offsets.keys()):
            wvpasseq(p.read(offsets[k]), (3, k * (1000 // len(k))))
        p.close()

        # this does some extra checks - do it explicitly
        store.close()

@wvtest
def test_basic_encrypted_repo():
    with no_lingering_errors(), create_test_config() as (tmpdir, store):
        src = os.path.join(tmpdir, b'src')
        os.mkdir(src)

        for i in range(100):
            open(os.path.join(src, b'%d' % i), 'wb').write(b'%d' % i)
