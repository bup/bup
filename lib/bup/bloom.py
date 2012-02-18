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
import sys, os, math, mmap
from bup import _helpers
from bup.helpers import *

BLOOM_VERSION = 2
MAX_BITS_EACH = 32 # Kinda arbitrary, but 4 bytes per entry is pretty big
MAX_BLOOM_BITS = {4: 37, 5: 29} # 160/k-log2(8)
MAX_PFALSE_POSITIVE = 1. # Totally arbitrary, needs benchmarking

_total_searches = 0
_total_steps = 0

bloom_contains = _helpers.bloom_contains
bloom_add = _helpers.bloom_add


class ShaBloom:
    """Wrapper which contains data from multiple index files. """
    def __init__(self, filename, f=None, readwrite=False, expected=-1):
        self.name = filename
        self.rwfile = None
        self.map = None
        assert(filename.endswith('.bloom'))
        if readwrite:
            assert(expected > 0)
            self.rwfile = f = f or open(filename, 'r+b')
            f.seek(0)

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
            pages = os.fstat(f.fileno()).st_size / 4096 * 5 # assume k=5
            self.delaywrite = expected > pages
            debug1('bloom: delaywrite=%r\n' % self.delaywrite)
            if self.delaywrite:
                self.map = mmap_readwrite_private(self.rwfile, close=False)
            else:
                self.map = mmap_readwrite(self.rwfile, close=False)
        else:
            self.rwfile = None
            f = f or open(filename, 'rb')
            self.map = mmap_read(f)
        got = str(self.map[0:4])
        if got != 'BLOM':
            log('Warning: invalid BLOM header (%r) in %r\n' % (got, filename))
            return self._init_failed()
        ver = struct.unpack('!I', self.map[4:8])[0]
        if ver < BLOOM_VERSION:
            log('Warning: ignoring old-style (v%d) bloom %r\n' 
                % (ver, filename))
            return self._init_failed()
        if ver > BLOOM_VERSION:
            log('Warning: ignoring too-new (v%d) bloom %r\n'
                % (ver, filename))
            return self._init_failed()

        self.bits, self.k, self.entries = struct.unpack('!HHI', self.map[8:16])
        idxnamestr = str(self.map[16 + 2**self.bits:])
        if idxnamestr:
            self.idxnames = idxnamestr.split('\0')
        else:
            self.idxnames = []

    def _init_failed(self):
        if self.map:
            self.map = None
        if self.rwfile:
            self.rwfile.close()
            self.rwfile = None
        self.idxnames = []
        self.bits = self.entries = 0

    def valid(self):
        return self.map and self.bits

    def __del__(self):
        self.close()

    def close(self):
        if self.map and self.rwfile:
            debug2("bloom: closing with %d entries\n" % self.entries)
            self.map[12:16] = struct.pack('!I', self.entries)
            if self.delaywrite:
                self.rwfile.seek(0)
                self.rwfile.write(self.map)
            else:
                self.map.flush()
            self.rwfile.seek(16 + 2**self.bits)
            if self.idxnames:
                self.rwfile.write('\0'.join(self.idxnames))
        self._init_failed()

    def pfalse_positive(self, additional=0):
        n = self.entries + additional
        m = 8*2**self.bits
        k = self.k
        return 100*(1-math.exp(-k*float(n)/m))**k

    def add_idx(self, ix):
        """Add the object to the filter, return current pfalse_positive."""
        if not self.map:
            raise Exception("Cannot add to closed bloom")
        self.entries += bloom_add(self.map, ix.shatable, self.bits, self.k)
        self.idxnames.append(os.path.basename(ix.name))

    def exists(self, sha):
        """Return nonempty if the object probably exists in the bloom filter.

        If this function returns false, the object definitely does not exist.
        If it returns true, there is a small probability that it exists
        anyway, so you'll have to check it some other way.
        """
        global _total_searches, _total_steps
        _total_searches += 1
        if not self.map:
            return None
        found, steps = bloom_contains(self.map, str(sha), self.bits, self.k)
        _total_steps += steps
        return found

    def __len__(self):
        return int(self.entries)


def create(name, expected, delaywrite=None, f=None, k=None):
    """Create and return a bloom filter for `expected` entries."""
    bits = int(math.floor(math.log(expected*MAX_BITS_EACH/8,2)))
    k = k or ((bits <= MAX_BLOOM_BITS[5]) and 5 or 4)
    if bits > MAX_BLOOM_BITS[k]:
        log('bloom: warning, max bits exceeded, non-optimal\n')
        bits = MAX_BLOOM_BITS[k]
    debug1('bloom: using 2^%d bytes and %d hash functions\n' % (bits, k))
    f = f or open(name, 'w+b')
    f.write('BLOM')
    f.write(struct.pack('!IHHI', BLOOM_VERSION, bits, k, 0))
    assert(f.tell() == 16)
    # NOTE: On some systems this will not extend+zerofill, but it does on
    # darwin, linux, bsd and solaris.
    f.truncate(16+2**bits)
    f.seek(0)
    if delaywrite != None and not delaywrite:
        # tell it to expect very few objects, forcing a direct mmap
        expected = 1
    return ShaBloom(name, f=f, readwrite=True, expected=expected)

