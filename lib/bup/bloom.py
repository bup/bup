"""Discussion of bloom constants for bup:

There are four basic things to consider when building a bloom filter:
The size, in bits, of the filter
The capacity, in entries, of the filter
The probability of a false positive that is tolerable
The number of bits readily available to use for addressing filter bits

There is one major tunable that is not directly related to the above:
k: the number of bits set in the filter per entry

Here's a wall of numbers showing the relationship between k; the ratio between
the filter size in bits and the entries in the filter; and pfalse_positive:

mn|k=3    |k=4    |k=5    |k=6    |k=7    |k=8    |k=9    |k=10   |k=11
 8|3.05794|2.39687|2.16792|2.15771|2.29297|2.54917|2.92244|3.41909|4.05091
 9|2.27780|1.65770|1.40703|1.32721|1.34892|1.44631|1.61138|1.84491|2.15259
10|1.74106|1.18133|0.94309|0.84362|0.81937|0.84555|0.91270|1.01859|1.16495
11|1.36005|0.86373|0.65018|0.55222|0.51259|0.50864|0.53098|0.57616|0.64387
12|1.08231|0.64568|0.45945|0.37108|0.32939|0.31424|0.31695|0.33387|0.36380
13|0.87517|0.49210|0.33183|0.25527|0.21689|0.19897|0.19384|0.19804|0.21013
14|0.71759|0.38147|0.24433|0.17934|0.14601|0.12887|0.12127|0.12012|0.12399
15|0.59562|0.30019|0.18303|0.12840|0.10028|0.08523|0.07749|0.07440|0.07468
16|0.49977|0.23941|0.13925|0.09351|0.07015|0.05745|0.05049|0.04700|0.04587
17|0.42340|0.19323|0.10742|0.06916|0.04990|0.03941|0.03350|0.03024|0.02870
18|0.36181|0.15765|0.08392|0.05188|0.03604|0.02748|0.02260|0.01980|0.01827
19|0.31160|0.12989|0.06632|0.03942|0.02640|0.01945|0.01549|0.01317|0.01182
20|0.27026|0.10797|0.05296|0.03031|0.01959|0.01396|0.01077|0.00889|0.00777
21|0.23591|0.09048|0.04269|0.02356|0.01471|0.01014|0.00759|0.00609|0.00518
22|0.20714|0.07639|0.03473|0.01850|0.01117|0.00746|0.00542|0.00423|0.00350
23|0.18287|0.06493|0.02847|0.01466|0.00856|0.00555|0.00392|0.00297|0.00240
24|0.16224|0.05554|0.02352|0.01171|0.00663|0.00417|0.00286|0.00211|0.00166
25|0.14459|0.04779|0.01957|0.00944|0.00518|0.00316|0.00211|0.00152|0.00116
26|0.12942|0.04135|0.01639|0.00766|0.00408|0.00242|0.00157|0.00110|0.00082
27|0.11629|0.03595|0.01381|0.00626|0.00324|0.00187|0.00118|0.00081|0.00059
28|0.10489|0.03141|0.01170|0.00515|0.00259|0.00146|0.00090|0.00060|0.00043
29|0.09492|0.02756|0.00996|0.00426|0.00209|0.00114|0.00069|0.00045|0.00031
30|0.08618|0.02428|0.00853|0.00355|0.00169|0.00090|0.00053|0.00034|0.00023
31|0.07848|0.02147|0.00733|0.00297|0.00138|0.00072|0.00041|0.00025|0.00017
32|0.07167|0.01906|0.00633|0.00250|0.00113|0.00057|0.00032|0.00019|0.00013

Here's a table showing available repository size for a given pfalse_positive
and three values of k (assuming we only use the 160 bit SHA1 for addressing the
filter and 8192bytes per object):

pfalse|obj k=4     |cap k=4    |obj k=5  |cap k=5    |obj k=6 |cap k=6
2.500%|139333497228|1038.11 TiB|558711157|4262.63 GiB|13815755|105.41 GiB
1.000%|104489450934| 778.50 TiB|436090254|3327.10 GiB|11077519| 84.51 GiB
0.125%| 57254889824| 426.58 TiB|261732190|1996.86 GiB| 7063017| 55.89 GiB

This eliminates pretty neatly any k>6 as long as we use the raw SHA for
addressing.

filter size scales linearly with repository size for a given k and pfalse.

Here's a table of filter sizes for a 1 TiB repository:

pfalse| k=3        | k=4        | k=5        | k=6
2.500%| 138.78 MiB | 126.26 MiB | 123.00 MiB | 123.37 MiB
1.000%| 197.83 MiB | 168.36 MiB | 157.58 MiB | 153.87 MiB
0.125%| 421.14 MiB | 307.26 MiB | 262.56 MiB | 241.32 MiB

For bup:
* We want the bloom filter to fit in memory; if it doesn't, the k pagefaults
per lookup will be worse than the two required for midx.
* We want the pfalse_positive to be low enough that the cost of sometimes
faulting on the midx doesn't overcome the benefit of the bloom filter.
* We have readily available 160 bits for addressing the filter.
* We want to be able to have a single bloom address entire repositories of
reasonable size.

Based on these parameters, a combination of k=4 and k=5 provides the behavior
that bup needs.  As such, I've implemented bloom addressing, adding and
checking functions in C for these two values.  Because k=5 requires less space
and gives better overall pfalse_positive performance, it is preferred if a
table with k=5 can represent the repository.

None of this tells us what max_pfalse_positive to choose.

Brandon Low <lostlogic@lostlogicx.com> 2011-02-04
"""

from contextlib import ExitStack
from tempfile import mkstemp
import builtins, os, math, struct

from bup import _helpers
from bup.helpers import \
    (debug1,
     debug2,
     finalized,
     log,
     mmap_read,
     mmap_readwrite,
     mmap_readwrite_private,
     notimplemented,
     unlink)
from bup.io import path_msg as pm


BLOOM_VERSION = 2
MAX_BITS_EACH = 32 # Kinda arbitrary, but 4 bytes per entry is pretty big
MAX_BLOOM_BITS = {4: 37, 5: 29} # 160/k-log2(8)
MAX_PFALSE_POSITIVE = 1. # Totally arbitrary, needs benchmarking

_total_searches = 0
_total_steps = 0

bloom_contains = _helpers.bloom_contains
bloom_add = _helpers.bloom_add


class _BloomBase:
    """Bloom filter elements shared across both readers and writers."""
    __slots__ = 'bits', 'entries', 'idxnames', 'k', 'map', 'path', 'version'
    # mmap not None indicates "open"

    # Should be completely replaced by subclasses so that all of the
    # context management / logic will be visible in one place.
    @notimplemented
    def __init__(self):
        # All __slots__ are required (these assignments just satisfy pylint)
        self.bits, self.entries, self.k, self.map = [None] * 4

    # Must be a context manager
    @notimplemented
    def __del__(self): pass
    @notimplemented
    def __enter__(self): return self
    @notimplemented
    def __exit__(self, type, value, traceback): pass

    def pfalse_positive(self, additional=0):
        assert self.map
        n = self.entries + additional
        m = 8*2**self.bits
        k = self.k
        return 100*(1-math.exp(-k*float(n)/m))**k

    def exists(self, sha):
        """Return nonempty if the object probably exists in the bloom filter.

        If this function returns false, the object definitely does not exist.
        If it returns true, there is a small probability that it exists
        anyway, so you'll have to check it some other way.
        """
        assert self.map
        global _total_searches, _total_steps
        _total_searches += 1
        if not self.map:
            return None
        found, steps = bloom_contains(self.map, sha, self.bits, self.k)
        _total_steps += steps
        return found

    def __len__(self):
        assert self.map
        return self.entries


class BloomInvalid(Exception): pass
class BloomNotFound(FileNotFoundError): pass


def _validate_and_get_info(path, data):
    got = data[0:4]
    if got != b'BLOM':
        raise BloomInvalid(f'invalid BLOM header ({pm(got)}) in {pm(path)}')
    ver = struct.unpack('!I', data[4:8])[0]
    if ver < BLOOM_VERSION:
        raise BloomInvalid(f'old-style (v{ver}) bloom {pm(path)}')
    if ver > BLOOM_VERSION:
        raise BloomInvalid(f'too-new (v{ver}) bloom {pm(path)}')
    bits, k, entries = struct.unpack('!HHI', data[8:16])
    idxnames = data[16 + 2**bits:]
    idxnames = idxnames.split(b'\0') if idxnames else []
    return ver, bits, k, entries, idxnames


class BloomReader(_BloomBase):
    # pylint: disable-next=super-init-not-called
    def __init__(self, path): # mmap not None indicates "open"
        """Open an existing bloom filter, read-only."""
        assert path.endswith(b'.bloom'), path
        self.map = None
        self.path = path
        with ExitStack() as ctx:
            try:
                file = ctx.enter_context(builtins.open(path, 'rb'))
            except FileNotFoundError as ex:
                raise BloomNotFound(ex.errno, ex.strerror, ex.filename) from ex
            self.map = ctx.enter_context(mmap_read(file, close=True))
            self.version, self.bits, self.k, self.entries, self.idxnames = \
                _validate_and_get_info(path, self.map)
            ctx.pop_all()
    def close(self):
        try:
            if self.map: self.map.close()
        finally:
            self.map = None
    def __del__(self): assert not self.map, self.path
    def __enter__(self): return self
    def __exit__(self, type, value, traceback): self.close()


def _create(path, expected, k):
    with ExitStack() as ctx:
        bits = int(math.floor(math.log(expected * MAX_BITS_EACH // 8, 2)))
        k = k or ((bits <= MAX_BLOOM_BITS[5]) and 5 or 4)
        if bits > MAX_BLOOM_BITS[k]:
            log('bloom: warning, max bits exceeded, non-optimal\n')
            bits = MAX_BLOOM_BITS[k]
        debug1(f'bloom: using 2^{bits:d} bytes and {k:d} hash functions\n')
        dir, name = os.path.split(path)
        fd, tmp = mkstemp(dir=dir or os.getcwdb(), prefix=(name + b'-'))
        with ExitStack() as ctx:
            ctx.enter_context(finalized(tmp, unlink))
            os.close(fd)
            tmp_file = ctx.enter_context(builtins.open(tmp, 'w+b'))
            tmp_file.write(b'BLOM')
            tmp_file.write(struct.pack('!IHHI', BLOOM_VERSION, bits, k, 0))
            assert tmp_file.tell() == 16
            # Assume POSIX truncate(), which requires zero-fill
            tmp_file.truncate(16+2**bits)
            tmp_file.seek(0)
            ctx.pop_all()
            return tmp_file, bits, k


def _open_write_map(file, expected):
    # Decide if we want to mmap() the pages as writable ('immediate'
    # write) or else map them privately for later writing back to
    # the file ('delayed' write).  A bloom table's write access
    # pattern is such that we dirty almost all the pages after adding
    # very few entries.  But the table is so big that dirtying
    # *all* the pages often exceeds Linux's default
    # /proc/sys/vm/dirty_ratio or /proc/sys/vm/dirty_background_ratio,
    # thus causing it to start flushing the table before we're
    # finished... even though there's more than enough space to
    # store the bloom table in RAM.
    #
    # To work around that behaviour, if we calculate that we'll
    # probably end up touching the whole table anyway (at least
    # one bit flipped per memory page), let's use a "private" mmap,
    # which defeats Linux's ability to flush it to disk.  Then we'll
    # flush it as one big lump during close().
    pages = os.fstat(file.fileno()).st_size // 4096 * 5 # assume k=5
    delaywrite = expected > pages
    debug1(f'bloom: delaywrite={delaywrite!r}\n')
    if delaywrite:
        data = mmap_readwrite_private(file, close=False)
    else:
        data = mmap_readwrite(file, close=False)
    return data, delaywrite


class BloomWriter(_BloomBase):

    __slots__ = ('_delaywrite', '_file', '_tmp_file_path')

    # pylint: disable-next=super-init-not-called
    def __init__(self, path, mode, expected, *, delaywrite=None, k=None):
        """Open (mode='r+b') an existing, or create (mode='w+b') a new
        bloom filter for updates.  The filter will not exist at path
        until the instance is successfully closed.

        """
        assert path.endswith(b'.bloom'), path
        assert expected > 0, expected
        # mmap not None indicates "open"
        self.map = None
        self._file = None
        self._tmp_file_path = None
        self.path = path

        # delaywrite arg is currently only used by tests
        def open_map(f):
            if delaywrite is not None and not delaywrite:
                # tell it to expect very few objects, forcing a direct mmap
                return _open_write_map(f, 1)
            return _open_write_map(f, expected)

        if mode ==  'wb':
            with ExitStack() as ctx:
                try:
                    self._file = ctx.enter_context(builtins.open(path, 'r+b'))
                except FileNotFoundError as ex:
                    raise BloomNotFound(ex.errno, ex.strerror, ex.filename) from ex
                self.map, self._delaywrite = open_map(self._file)
                ctx.enter_context(self.map)
                self.version, self.bits, self.k, self.entries, self.idxnames = \
                    _validate_and_get_info(path, self.map)
                dir, name = os.path.split(path)
                fd, tmp = mkstemp(dir=dir or os.getcwdb(), prefix=name)
                self._tmp_file_path = tmp
                os.close(fd)
                os.rename(path, tmp)
                ctx.pop_all()
            return

        assert mode == 'w+b', mode # new filter
        assert expected > 0, expected
        self.entries = 0
        self.idxnames = []
        self.version = BLOOM_VERSION
        self._file, self.bits, self.k = _create(path, expected, k)
        self._tmp_file_path = self._file.name
        with ExitStack() as ctx:
            ctx.enter_context(finalized(self._tmp_file_path, unlink))
            ctx.enter_context(self._file)
            self.map, self._delaywrite = open_map(self._file)
            ctx.pop_all()

    def close(self, error=None):
        try:
            with ExitStack() as ctx:
                if self._tmp_file_path:
                    ctx.enter_context(finalized(self._tmp_file_path, unlink))
                if self._file:
                    ctx.enter_context(self._file)
                if self.map:
                    ctx.enter_context(self.map)
                if error:
                    log(f'dropping unfinished bloom {pm(self.path)}, interrupted by {str(error)}')
                    return
                if not self._file and self.map:
                    return
                debug2(f'bloom: closing with {self.entries} entries\n')
                self.map[12:16] = struct.pack('!I', self.entries)
                if self._delaywrite:
                    self._file.seek(0)
                    self._file.write(self.map)
                else:
                    self.map.flush()
                self._file.seek(16 + 2**self.bits)
                if self.idxnames:
                    self._file.write(b'\0'.join(self.idxnames))
                os.rename(self._tmp_file_path, self.path)
        finally:
            self._file, self.map, self._tmp_file_path = None, None, None

    def __del__(self): assert not self.map, self.path
    def __enter__(self): return self
    def __exit__(self, type, value, traceback): self.close(value)

    def add(self, ids):
        """Add the hashes in ids (packed binary 20-bytes) to the filter."""
        if not self.map:
            raise Exception("Cannot add to closed bloom")
        self.entries += bloom_add(self.map, ids, self.bits, self.k)

    def add_idx(self, ix):
        """Add the object to the filter."""
        assert self.map
        self.add(ix.shatable)
        self.idxnames.append(os.path.basename(ix.name))


def clear_bloom(dir):
    unlink(os.path.join(dir, b'bup.bloom'))
