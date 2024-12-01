
from contextlib import ExitStack
import glob, os, struct

from bup import _helpers
from bup.compat import pending_raise
from bup.helpers import log, mmap_read
from bup.io import path_msg


MIDX_HEADER = b'MIDX'
MIDX_VERSION = 4

extract_bits = _helpers.extract_bits
_total_searches = 0
_total_steps = 0


def _midx_header(mmap): return mmap[0:4]
def _midx_version(mmap): return struct.unpack('!I', mmap[4:8])[0]


class MissingIdxs(Exception):
    __slots__ = 'paths',
    def __init__(self, *, paths):
        super().__init__()
        self.paths = paths

class PackMidx:
    """Wrapper which contains data from multiple index files.  Create
    via open_midx(), not PackMidx().  Multiple index (.midx) files
    constitute a wrapper around index (.idx) files and make it
    possible for bup to expand Git's indexing capabilities to vast
    amounts of files.  This class only supports the current
    MIDX_VERSION.

    """
    def __init__(self, filename, mmap, *, _internal=False):
        """Takes ownership of mmap."""
        with ExitStack() as contexts:
            contexts.enter_context(mmap)
            assert _internal, 'call open_midx()'
            assert _midx_header(mmap) == MIDX_HEADER
            assert _midx_version(mmap) == MIDX_VERSION
            self.map = mmap
            self.closed = False
            self.name = filename
            self.bits = _helpers.firstword(self.map[8:12])
            self.entries = 2**self.bits
            self.fanout_ofs = 12
            # fanout len is self.entries * 4
            self.sha_ofs = self.fanout_ofs + self.entries * 4
            self.nsha = self._fanget(self.entries - 1)
            # sha table len is self.nsha * 20
            self.which_ofs = self.sha_ofs + 20 * self.nsha
            # which len is self.nsha * 4
            self.idxnames = self.map[self.which_ofs + 4 * self.nsha:].split(b'\0')
            # REVIEW: idx paths always relative to midx path?
            idxdir = os.path.dirname(filename) + b'/'
            missing = []
            for name in self.idxnames:
                if not os.path.exists(idxdir + name):
                    self.missing.append(name)
            if missing:
                raise MissingIdxs(paths=missing)
            contexts.pop_all()

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        with pending_raise(value, rethrow=False):
            self.close()

    def _fanget(self, i):
        if i >= self.entries * 4 or i < 0:
            raise IndexError('invalid midx index %d' % i)
        ofs = self.fanout_ofs + i * 4
        return _helpers.firstword(self.map[ofs : ofs + 4])

    def _get(self, i):
        if i >= self.nsha or i < 0:
            raise IndexError('invalid midx index %d' % i)
        ofs = self.sha_ofs + i * 20
        return self.map[ofs : ofs + 20]

    def _get_idx_i(self, i):
        if i >= self.nsha or i < 0:
            raise IndexError('invalid midx index %d' % i)
        ofs = self.which_ofs + i * 4
        return struct.unpack_from('!I', self.map, offset=ofs)[0]

    def _get_idxname(self, i):
        return self.idxnames[self._get_idx_i(i)]

    def close(self):
        self.closed = True
        if self.map is not None:
            self.fanout = self.shatable = self.whichlist = self.idxnames = None
            self.map.close()
            self.map = None

    def __del__(self):
        assert self.closed

    def exists(self, hash, want_source=False):
        """Return nonempty if the object exists in the index files."""
        global _total_searches, _total_steps
        _total_searches += 1
        want = hash
        el = extract_bits(want, self.bits)
        if el:
            start = self._fanget(el-1)
            startv = el << (32-self.bits)
        else:
            start = 0
            startv = 0
        end = self._fanget(el)
        endv = (el+1) << (32-self.bits)
        _total_steps += 1   # lookup table is a step
        hashv = _helpers.firstword(hash)
        #print '(%08x) %08x %08x %08x' % (extract_bits(want, 32), startv, hashv, endv)
        while start < end:
            _total_steps += 1
            #print '! %08x %08x %08x   %d - %d' % (startv, hashv, endv, start, end)
            mid = start + (hashv - startv) * (end - start - 1) // (endv - startv)
            #print '  %08x %08x %08x   %d %d %d' % (startv, hashv, endv, start, mid, end)
            v = self._get(mid)
            #print '    %08x' % self._num(v)
            if v < want:
                start = mid+1
                startv = _helpers.firstword(v)
            elif v > want:
                end = mid
                endv = _helpers.firstword(v)
            else: # got it!
                return want_source and self._get_idxname(mid) or True
        return None

    def __iter__(self):
        start = self.sha_ofs
        for ofs in range(start, start + self.nsha * 20, 20):
            yield self.map[ofs : ofs + 20]

    def __len__(self):
        return int(self.nsha)


def open_midx(path, *, ignore_missing=True):
    """Return a PackMidx for path.  Return None if path exists but is
    either too old or too new.  If any of the constituent indexes are
    missing, raise MissingIdxs if ignore_missing is false otherwise
    return None.

    """
    # FIXME: eventually note_error when not raising?
    assert path.endswith(b'.midx') # FIXME: wanted/needed?
    mmap = mmap_read(open(path))
    with ExitStack() as contexts:
        contexts.enter_context(mmap)
        if _midx_header(mmap) != MIDX_HEADER:
            pathm = path_msg(path)
            log(f'Warning: skipping: invalid MIDX header in {pathm}\n')
            return None
        ver = _midx_version(mmap)
        if ver == MIDX_VERSION:
            if not ignore_missing:
                contexts.pop_all()
                return PackMidx(path, mmap, _internal=True)
            missing = None
            contexts.pop_all()
            try:
                midx = PackMidx(path, mmap, _internal=True)
            except MissingIdxs as ex:
                missing = ex.paths
            if not missing:
                return midx
            pathm = path_msg(path)
            for missing in ex.paths:
                imsg = path_msg(missing)
                log(f'Warning: ignoring midx {pathm} (missing idx {imsg})\n')
            return None
        pathm = path_msg(path)
        if ver < MIDX_VERSION:
            log(f'Warning: ignoring old-style (v{ver}) midx {pathm}\n')
        elif ver > MIDX_VERSION:
            log(f'Warning: ignoring too-new (v{ver}) midx {pathm}\n')
        return None


def clear_midxes(dir=None):
    for midx in glob.glob(os.path.join(dir, b'*.midx')):
        os.unlink(midx)
