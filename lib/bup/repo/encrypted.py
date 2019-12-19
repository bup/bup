"""
Encrypted repository.

The encrypted repository stores all files in encrypted form in any
kind of bup.storage.BupStorage backend, we store the following
types of files
 * configuration files (bup.storage.Kind.CONFIG)
 * pack files (bup.storage.Kind.DATA & bup.storage.Kind.METADATA)
 * idx files (bup.storage.Kind.IDX)

We also cache the idx files locally in unencrypted form, so that we
can generate midx files or look up if an object already exists.


The encryption design should have the following properties:
 1) The data cannot be tampered with at rest without this being
    detected, at least at restore time.
 2) Random access to objects in the (data) packs must be possible.
 3) It should not be possible for an attacker to check if a given
    object (e.g. an image) is contained in a backup.
 4) It should be possible to configure truly append-only backups,
    i.e. backups that even the system making them cannot restore.
    (This serves to prevent a compromised system from accessing
    data that was previously backed up.)

This has the following implications:

 - CTR mode and similar are out, making block-based encryption
   more expensive (actually expand the block due to the MAC)
   (this follows from 1).
 - Either block-based or object-based encryption must be used
   for pack files (follows from 2).
 - From 3, it follows that
   - idx files must be encrypted (at least they store the sha1
     of smaller files), and
   - the hashsplit algorithm needs to be keyed (to prevent any
     fingerprinting of the blob size sequence).
 - Public key encryption should be used for data (to enable 4)


So based on this, the design is the following:

Each repository has two keys:
 1) The (symmetric) 'repokey;, used to encrypt configuration and
    index data.
 2) The (asymmetric) data key (the public part is the 'writekey',
    the private part is the 'readkey')

To access the repository, at least the 'repokey' and one of the
other two keys must be available. Each key enables the following:
 - repokey
   - ref updates
   - idx file creation/reading
     (and consequently existence checks)
 - writekey
   - data pack creation
 - readkey
   - data access

There are different files stored in the repository:
 - refs
   An encrypted JSON-encoded file that contains the refs for the
   repository, stored as a single object in a container described
   below.
 - pack-*.encpack
   Encrypted pack files (not in git format, see below) containing
   the actual data; note that the filename is randomly generated
   (not based on the content like in git).
 - pack-*.encidx
   Encrypted idx files corresponding to the pack-*.encpack files;
   their content is stored in a single object inside the container
   file (see below) and is (currently) just the git/bup compatible
   PackIdxV2.

Each file stored in the repository has the following format, all
values are stored in little endian:

| offsets | data
|  0 -  3 | magic 0x420x550x500x65 ("BUPe")
+
|  4      | header algorithm flags/identifier, currently only
|         | 1 - for libsodium sealed box (data files)
|         | 2 - for libsodium secret box (config/idx files)
+
|  5      | reserved, must be 0
+
|  6 -  7 | length of the encrypted header (EH)
+
|  8 -  H | (H := EH + 8)
|         | encrypted header, with the following format:
|         |
|         |  | 0      | header format
|         |  |        |  1 - this format
|         |  +
|         |  | 1      | data algorithm flags/identifier,
|         |  |        |  1 - for libsodium secret box and
|         |  |        |      libsodium::crypto_stream() for
|         |  |        |      the object size vuint
|         |  +
|         |  | 2      | file type:
|         |  |        |  1 - pack
|         |  |        |  2 - idx (V2)
|         |  |        |  3 - config
|         |  +
|         |  | 3      | compression type
|         |  |        |  1 - zlib
|         |  +
|         |  | 4 - EH | secret key for the remainder of the file
...
|         | encrypted objects

This construction is somewhat wasteful (in the data case) since the
libsodium sealed box already uses an ephemeral key for the encryption;
we could use it for all the data, however, it's only 8 bytes or so
and not worth the extra complexity.

The encrypted objects in the file are prefixed by their encrypted
size (encoded as a vuint before encryption, with a limit of 1 GiB).
The size vuint is currently encrypted using crypto_stream() with a
nonce derived from its position in the file ("0x80 0 ... 0 offset").
The object data is compressed and then prefixed by a type byte (in
git packs, the type encoded as the lowest 3 bits of the size vuint).
The result is then stored in a libsodium secret box, using a similar
nonce ("0 ... 0 offset", which is the same without the top bit set).
The secret box provides authentication, and the nonce construction
protects against an attacker reordering chunks in the file to affect
restored data.


Encrypted repositories are config-file based repositories, and need
to be configured as follows:

[bup.repo "test"]
  type = encrypted
  storage = File        # or any other supported storage type
  # storage options, e.g. "path = " for File storage
  cachedir = /some/dir  # cache directory (for unencrypted idx files
                        # and refs data
  separatemeta = True   # (or False), indicates if metadata (tree and
                        # commit objects, bupm files), i.e. data that
                        # is needed for e.g. 'bup ls' or 'bup fuse' is
                        # stored in separate packs, to avoid download
                        # of everything in order to restore
  # use 'bup genkey' to generate keys
  repokey = <hex key>   # (symmetric) repokey, described above, for the
                        # crypto currently implemented this is a 32-byte
                        # random key hex-encoded
  readkey = <hex key>   # repo read/store key (private part of the
                        # asymmetric key pair), also 32 bytes in hex
  writekey = <hex key>  # repo write key (public part of the asymmetric
                        # key pair), also 32 bytes in hex
"""

# TODO
#  * keep metadata packs locally (if split out? configurable?
#    encrypted?)
#  * repo config
#    - stored in repo
#    - symmetrically encrypted using repokey
#    - have a version number and reject != 1
#  * hashsplit permutation
#    - do we still want it, now that sizes are encrypted?
#    - if so randomly create on init and store in repo config
#  * teach PackIdxList that there may be a limit on open files
#    (and mmap addres space)
#  * address TODOs below in the code

from __future__ import absolute_import
import os
import struct
import zlib
import json
import glob
import fnmatch
from io import BytesIO
from binascii import hexlify, unhexlify
from itertools import islice

try:
    import libnacl.secret
    import libnacl.sealed
except ImportError:
    libnacl = None

from bup import compat, git, vfs
from bup.helpers import mkdirp, Sha1
from bup.vint import read_vuint, pack
from bup.storage import get_storage, FileNotFound, Kind
from bup.compat import bytes_from_uint, byte_int
from bup.repo import ConfigRepo


READ_SIZE = 1024 * 1024
# 1 GiB is the most we're willing to store as a single object
# (this is after compression and encryption)
MAX_ENC_BLOB = 1024 * 1024 * 1024
MAX_ENC_BLOB_VUINT_LEN = len(pack('V', MAX_ENC_BLOB))


class EncryptedVuintReader:
    def __init__(self, file, vuint_cs):
        self.file = file
        self.vuint_cs = [byte_int(x) for x in vuint_cs]
        self.offs = 0

    def read(self, sz):
        assert sz == 1
        v = byte_int(self.file.read(1)[0])
        ret = bytes_from_uint(v ^ self.vuint_cs[self.offs])
        self.offs += 1
        assert self.offs < len(self.vuint_cs)
        return ret

class EncryptedContainer(object):
    HEADER, OBJ, FOOTER = range(3)

    def __init__(self, storage, name, mode, kind, compression=1,
                 key=None, idxwriter=None, overwrite=None):
        self.file = None # for __del__ in case of exceptions
        assert mode in ('r', 'w')
        assert compression in range(1, 10)
        self.mode = mode
        self.compression = compression
        self.idxwriter = idxwriter

        if kind == Kind.DATA or kind == Kind.METADATA:
            self.filetype = 1
            header_alg = 1
        elif kind == Kind.IDX:
            self.filetype = 2
            header_alg = 2
        elif kind == Kind.CONFIG:
            self.filetype = 3
            header_alg = 2
        else:
            assert False, 'Invalid kind %d' % kind
        if header_alg == 1:
            self.ehlen = 84
        elif header_alg == 2:
            self.ehlen = 76
        else:
            assert False
        self.headerlen = self.ehlen + 8 # hdrlen

        if mode == 'r':
            self.file = storage.get_reader(name, kind)
            hdr = self.file.read(8)
            assert hdr[:4] == b'BUPe'
            enc, res, ehlen = struct.unpack('<BBH', hdr[4:])
            assert enc == header_alg
            assert res == 0
            assert ehlen == self.ehlen
            if header_alg == 1:
                assert isinstance(key, libnacl.public.SecretKey)
                hdrbox = libnacl.sealed.SealedBox(key)
            else:
                assert key is not None
                hdrbox = libnacl.secret.SecretBox(key)
            inner_hdr = hdrbox.decrypt(self.file.read(ehlen))
            del hdrbox
            (fmt, alg, tp, compr) = struct.unpack('<BBBB', inner_hdr[:4])
            assert fmt == 1
            assert alg == 1
            assert tp == self.filetype, "type %d doesn't match %d (%s)" % (tp, self.filetype, name)
            assert compr == 1
            self.box = libnacl.secret.SecretBox(inner_hdr[4:])
            self._check = None
            self.offset = self.headerlen
        else:
            assert key is not None
            self.file = storage.get_writer(name, kind, overwrite=overwrite)
            self.box = libnacl.secret.SecretBox()
            inner_hdr = struct.pack('<BBBB', 1, 1, self.filetype, 1)
            inner_hdr += self.box.sk
            if header_alg == 1:
                hdrbox = libnacl.sealed.SealedBox(key)
            else:
                hdrbox = libnacl.secret.SecretBox(key)
            eh = hdrbox.encrypt(inner_hdr)
            assert len(eh) == self.ehlen
            del hdrbox
            hdr = b'BUPe'
            hdr += struct.pack('<BxH', header_alg, len(eh))
            hdr += eh
            self.offset = 0
            self._write(hdr, self.HEADER)
            assert self.offset == self.headerlen

    def __del__(self):
        if self.file is None:
            return
        if self.mode == 'w':
            self.abort()
        else:
            self.close()

    @property
    def nonce(self):
        return struct.pack('>16xQ', self.offset)

    @property
    def lnonce(self):
        return struct.pack('>B15xQ', 0x80, self.offset)

    def _write(self, data, dtype, objtype=None):
        assert self.mode == 'w'
        if dtype == self.OBJ:
            z = zlib.compressobj(self.compression)
            objtypeb = struct.pack('B', objtype)
            data = z.compress(objtypeb) + z.compress(data) + z.flush()
        if dtype in (self.OBJ, self.FOOTER):
            data = self.box.encrypt(data, self.nonce, pack_nonce=False)[1]
        if dtype == self.OBJ:
            assert len(data) <= MAX_ENC_BLOB
            vuint = pack('V', len(data))
            encvuint = libnacl.crypto_stream_xor(vuint, self.lnonce,
                                                 self.box.sk)
            data = encvuint + data
        self.file.write(data)
        retval = self.offset
        self.offset += len(data)
        return retval

    def write(self, objtype, sha, data):
        offs = self._write(data, self.OBJ, objtype)
        if self.idxwriter:
            # Set the crc to the objtype - we cannot copy any objects
            # from one pack file to another without decrypting anyway
            # as the encryption nonce is the file offset, and we have
            # authentication as part of the encryption... but it may
            # be useful to have the objtype in case we need to e.g.
            # attempt to recover all commits (if refs are lost) etc.
            self.idxwriter.add(sha, objtype, offs)
        return offs

    def finish(self):
        assert self.mode == 'w'
        self.file.close()
        self.file = None
        self._cleanup()

    @property
    def size(self):
        assert self.mode == 'w'
        if self.file:
            return self.offset + self.headerlen
        return self.offset

    def abort(self):
        assert self.mode == 'w'
        self.file.abort()
        self.file = None
        self._cleanup()

    def _cleanup(self):
        if self.mode == 'w':
            del self.box
        elif self.file is not None:
            self.file.close()
        self.file = None

    def read(self, offset=None):
        assert self.mode == 'r'
        self.offset = offset or self.headerlen
        self.file.seek(self.offset)
        vuint_cs = libnacl.crypto_stream(MAX_ENC_BLOB_VUINT_LEN,
                                         self.lnonce, self.box.sk)
        sz = read_vuint(EncryptedVuintReader(self.file, vuint_cs))
        assert sz <= MAX_ENC_BLOB
        data = self.file.read(sz)
        assert len(data) == sz
        data = self.box.decrypt(data, self.nonce)
        data = zlib.decompress(data)
        objtype = struct.unpack('B', data[:1])[0]
        return objtype, data[1:]

    def close(self):
        assert self.mode == 'r'
        if self.file is None:
            return
        self.file.close()
        self.file = None
        self._cleanup()


class EncryptedRepo(ConfigRepo):
    """
    Implement the Repo abstraction, but store the data in an encrypted fashion.
    """
    def __init__(self, cfg_file, create=False):
        super(EncryptedRepo, self).__init__(cfg_file, create)
        # init everything for __del__ in case we get an exception here
        self.storage = None
        self.data_writer = None
        self.meta_writer = None
        self.cfg_file = cfg_file
        self.ec_cache = {}

        if libnacl is None:
            raise Exception("Encrypted repositories require libnacl")

        self.max_pack_size = self.config(b'git.packSizeLimit', opttype='int',
                                         default=1000 * 1000 * 1000)
        self.cachedir = self.config(b'bup.cachedir')
        if self.cachedir is None:
            raise Exception("encrypted repositories need a 'cachedir'")
        if create:
            mkdirp(self.cachedir)
        if not os.path.isdir(self.cachedir):
            raise Exception("cachedir doesn't exist or isn't a directory - may have to init the repo?")
        self.storage = get_storage(self, create=create)

        self.readkey = None
        self.repokey = None
        self.writekey = None
        readkey = self.config(b'bup.readkey')
        if readkey is not None:
            self.readkey = libnacl.public.SecretKey(unhexlify(readkey))
        repokey = self.config(b'bup.repokey')
        if repokey is not None:
            self.repokey = unhexlify(repokey)
        writekey = self.config(b'bup.writekey')
        if writekey is not None:
            self.writekey = unhexlify(writekey)
            if self.readkey is not None:
                assert self.writekey == self.readkey.pk
        else:
            assert self.readkey is not None, "at least one of 'readkey' or 'writekey' is required"
            self.writekey = self.readkey.pk

        self.compression = self.config(b'bup.compression', opttype='int',
                                       default=1)
        self.separatemeta = self.config(b'bup.separatemeta', opttype='bool')

        self._synchronize_idxes()

        # TODO: remove ignore_midx and teach git.PackIdxList to do the lookup
        #       in the correct idx file again?
        self.idxlist = git.PackIdxList(self.cachedir, ignore_midx=True)

    def _synchronize_idxes(self):
        changes = False
        local_idxes = set(fnmatch.filter(os.listdir(self.cachedir), b'*.idx'))
        for remote_idx in self.storage.list(b'*.encidx'):
            local_idx = remote_idx.replace(b'.encidx', b'.idx')
            if local_idx in local_idxes:
                local_idxes.remove(local_idx)
            else:
                ec = self._open_read(remote_idx, Kind.IDX)
                with open(os.path.join(self.cachedir, local_idx), 'wb') as f:
                    f.write(ec.read()[1])
                changes = True
        for local_idx in local_idxes:
            changes = True
            os.unlink(os.path.join(self.cachedir, local_idx))

        if changes:
            git.auto_midx(self.cachedir)

    def _create_new_pack(self, kind):
        fakesha = libnacl.randombytes(20)
        hexsha = hexlify(fakesha)
        return fakesha, EncryptedContainer(self.storage,
                                           b'pack-%s.encpack' % hexsha, 'w',
                                           kind, self.compression,
                                           key=self.writekey,
                                           idxwriter=git.PackIdxV2Writer())

    def _ensure_data_writer(self):
        if self.data_writer is not None and self.data_writer.size > self.max_pack_size:
            self.data_writer.close()
            if self.meta_writer == self.data_writer:
                self.meta_writer = None
            self.data_writer = None
        if self.data_writer is None:
            self.data_fakesha, self.data_writer = self._create_new_pack(Kind.DATA)

    def _ensure_meta_writer(self):
        if self.meta_writer is not None and self.meta_writer.size > self.max_pack_size:
            self.meta_writer.close()
            self.meta_writer = None
        if self.meta_writer is None:
            if self.separatemeta:
                self.meta_fakesha, self.meta_writer = self._create_new_pack(Kind.METADATA)
            else:
                self._ensure_data_writer()
                self.meta_writer = self.data_writer

    def close(self):
        self.abort_writing()
        for ec in self.ec_cache.values():
            ec.close()
        self.ec_cache = {}
        if self.storage is not None:
            self.storage.close()
            self.storage = None

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def _encode_refs(self, refs):
        ret = {}
        for k, v in refs.items():
            ret[hexlify(k).decode('ascii')] = v.decode('ascii')
        return ret

    def _decode_refs(self, encrefs):
        ret = {}
        for k, v in encrefs.items():
            ret[unhexlify(k)] = v.encode('ascii')
        return ret

    def update_ref(self, refname, newval, oldval):
        self.finish_writing()
        readfile, refs = self._json_refs()
        if oldval:
            assert refs[refname] == hexlify(oldval)
        refs[refname] = hexlify(newval)
        refs = self._encode_refs(refs)
        reffile = EncryptedContainer(self.storage, b'refs', 'w',
                                     Kind.CONFIG, self.compression,
                                     key=self.repokey,
                                     overwrite=readfile)
        reffile.write(0, None, json.dumps(refs).encode('utf-8'))
        reffile.finish()

    def _open_read(self, name, kind, cache=False):
        if not name in self.ec_cache:
            if kind == Kind.IDX or kind == Kind.CONFIG:
                key = self.repokey
            elif kind == Kind.DATA or kind == Kind.METADATA:
                key = self.readkey
            else:
                assert False
            self.ec_cache[name] = EncryptedContainer(self.storage, name, 'r',
                                                     kind, key=key)
        return self.ec_cache[name]

    def _json_refs(self):
        try:
            reffile = self._open_read(b'refs', Kind.CONFIG)
            data = reffile.read()[1]
            return reffile.file, self._decode_refs(json.loads(data.decode('utf-8')))
        except FileNotFound:
            return None, {}

    def refs(self, patterns=None, limit_to_heads=False, limit_to_tags=False):
        _, refs = self._json_refs()
        # git pattern matching (in show-ref) matches only full components
        # of the /-split ref, so split the patterns by / and then later ...
        if patterns is None:
            patterns = [[]]
        else:
            patterns = [p.split(b'/') for p in patterns]
        for ref in refs:
            # we check if the found ref ends with any of the patterns
            # (after splitting by / as well, to match only full components)
            refpath = ref.split(b'/')
            found = False
            for pattern in patterns:
                if refpath[-len(pattern):] == pattern:
                    found = True
                    break
            if not found:
                continue
            if limit_to_heads and not ref.startswith(b'refs/heads/'):
                continue
            if limit_to_tags and not ref.startswith(b'refs/tags/'):
                continue
            yield ref, unhexlify(refs[ref])

    def read_ref(self, ref):
        refs = self.refs(patterns=[ref], limit_to_heads=True)
        # TODO: copied from git.read_ref()
        l = tuple(islice(refs, 2))
        if l:
            assert(len(l) == 1)
            return l[0][1]
        else:
            return None

    def rev_list(self, ref_or_refs, count=None, parse=None, format=None):
        # TODO: maybe we should refactor this to not have all of bup rely
        # on the git format ... it's ugly that we have to produce it here
        #
        # TODO: also, this is weird, I'm using existing bup functionality
        # to pretend I'm git, and then bup uses that again, really it stands
        # to reason that bup should do this itself without even *having* a
        # rev_list() method that calls out to git - and it'll probably be
        # faster too since we have the bloom/midx.
        assert count is None
        assert format in (b'%T %at', None)
        # TODO: ugh, this is a messy API ...
        if isinstance(ref_or_refs, compat.str_type):
            ref = ref_or_refs
        else:
            assert len(ref_or_refs) == 1
            ref = ref_or_refs[0]
        while True:
            commit = git.parse_commit(git.get_cat_data(self.cat(ref), b'commit'))
            if format is None:
                yield ref
            else:
                if format == b'%T %at':
                    data = BytesIO(b'%s %d\n' % (commit.tree, commit.author_sec))
                yield (ref, parse(data))
            if not commit.parents:
                break
            ref = commit.parents[0]

    def is_remote(self):
        # return False so we don't have to implement resolve()
        return False

    def cat(self, ref):
        """If ref does not exist, yield (None, None, None).  Otherwise yield
        (oidx, type, size), and then all of the data associated with
        ref.

        """
        if len(ref) == 40 and all([x in b'0123456789abcdefABCDEF' for x in ref]):
            oid = unhexlify(ref)
        else:
            oid = self.read_ref(ref)
            if oid is None:
                raise Exception("ref %r not found in repo" % ref)
        oidx = hexlify(oid)
        res = self.idxlist.exists(oid,
                                  want_source=True,
                                  want_offs=True)
        if res is None:
            yield (None, None, None)
            return
        where, offs = res
        assert where.startswith(b'pack-') and where.endswith(b'.idx')
        where = where.replace(b'.idx', b'.encpack')
        # Kind.DATA / Kind.METADATA are equivalent here
        ec = self._open_read(where, Kind.DATA, cache=True)
        objtype, data = ec.read(offs)
        yield (oidx, git._typermap[objtype], len(data))
        yield data

    def join(self, ref):
        return vfs.join(self, ref)

    def _data_write(self, objtype, content):
        sha = Sha1(content).digest()
        if not self.exists(sha):
            self._ensure_data_writer()
            self.data_writer.write(objtype, sha, content)
        self.idxlist.add(sha)
        return sha

    def _meta_write(self, objtype, content):
        sha = Sha1(content).digest()
        if not self.exists(sha):
            self._ensure_meta_writer()
            self.meta_writer.write(objtype, sha, content)
        self.idxlist.add(sha)
        return sha

    def write_commit(self, tree, parent,
                     author, adate_sec, adate_tz,
                     committer, cdate_sec, cdate_tz,
                     msg):
        content = git.create_commit_blob(tree, parent,
                                         author, adate_sec, adate_tz,
                                         committer, cdate_sec, cdate_tz,
                                         msg)
        return self._meta_write(1, content)

    def write_tree(self, shalist=None, content=None):
        assert shalist is None or content is None
        if content is None:
            content = git.tree_encode(shalist)
        return self._meta_write(2, content)

    def write_data(self, data):
        return self._data_write(3, data)

    def write_symlink(self, target):
        return self._meta_write(3, target)

    def write_bupm(self, data):
        return self._meta_write(3, data)

    def just_write(self, sha, type, content):
        # TODO: teach bup-get to differentiate the type of data/metadata
        return self._data_write(git._typemap[type], data)

    def exists(self, sha, want_source=False):
        return self.idxlist.exists(sha, want_source=want_source)

    def _finish(self, writer, fakesha, meta=False):
        hexsha = hexlify(fakesha)
        idxname = os.path.join(self.cachedir, b'pack-%s.idx' % hexsha)
        writer.finish()
        writer.idxwriter.write(idxname, fakesha)
        encidx = EncryptedContainer(self.storage, b'pack-%s.encidx' % hexsha,
                                    'w', Kind.IDX, self.compression,
                                    key=self.repokey)
        encidx.write(0, None, open(idxname, 'rb').read())
        encidx.finish()

    def finish_writing(self, run_midx=True):
        if self.meta_writer != self.data_writer and self.meta_writer is not None:
            self._finish(self.meta_writer, self.meta_fakesha, meta=True)
            self.meta_writer = None
        if self.data_writer is not None:
            self._finish(self.data_writer, self.data_fakesha)
            if self.meta_writer == self.data_writer:
                self.meta_writer = None
            self.data_writer = None
        if run_midx:
            git.auto_midx(self.cachedir)

    def abort_writing(self):
        if self.meta_writer != self.data_writer and self.meta_writer is not None:
            self.meta_writer.abort()
            self.meta_writer = None
        if self.data_writer is not None:
            self.data_writer.abort()
            if self.meta_writer == self.data_writer:
                self.meta_writer = None
            self.data_writer = None
