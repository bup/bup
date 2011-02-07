"""Git interaction library.
bup repositories are in Git format. This library allows us to
interact with the Git data structures.
"""
import os, sys, zlib, time, subprocess, struct, stat, re, tempfile, math, glob
from bup.helpers import *
from bup import _helpers, path

MIDX_VERSION = 4

"""Discussion of bloom constants for bup:

There are four basic things to consider when building a bloom filter:
The size, in bits, of the filter
The capacity, in entries, of the filter
The probability of a false positive that is tolerable
The number of bits readily available to use for addresing filter bits

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
and gives better overall pfalse_positive perofrmance, it is preferred if a
table with k=5 can represent the repository.

None of this tells us what max_pfalse_positive to choose.

Brandon Low <lostlogic@lostlogicx.com> 04-02-2011
"""
BLOOM_VERSION = 2
MAX_BITS_EACH = 32 # Kinda arbitrary, but 4 bytes per entry is pretty big
MAX_BLOOM_BITS = {4: 37, 5: 29} # 160/k-log2(8)
MAX_PFALSE_POSITIVE = 1. # Totally arbitrary, needs benchmarking

verbose = 0
ignore_midx = 0
home_repodir = os.path.expanduser('~/.bup')
repodir = None

_typemap =  { 'blob':3, 'tree':2, 'commit':1, 'tag':4 }
_typermap = { 3:'blob', 2:'tree', 1:'commit', 4:'tag' }

_total_searches = 0
_total_steps = 0


class GitError(Exception):
    pass


def repo(sub = ''):
    """Get the path to the git repository or one of its subdirectories."""
    global repodir
    if not repodir:
        raise GitError('You should call check_repo_or_die()')

    # If there's a .git subdirectory, then the actual repo is in there.
    gd = os.path.join(repodir, '.git')
    if os.path.exists(gd):
        repodir = gd

    return os.path.join(repodir, sub)


def auto_midx(objdir):
    args = [path.exe(), 'midx', '--auto', '--dir', objdir]
    try:
        rv = subprocess.call(args, stdout=open('/dev/null', 'w'))
    except OSError, e:
        # make sure 'args' gets printed to help with debugging
        add_error('%r: exception: %s' % (args, e))
        raise
    if rv:
        add_error('%r: returned %d' % (args, rv))

    args = [path.exe(), 'bloom', '--dir', objdir]
    try:
        rv = subprocess.call(args, stdout=open('/dev/null', 'w'))
    except OSError, e:
        # make sure 'args' gets printed to help with debugging
        add_error('%r: exception: %s' % (args, e))
        raise
    if rv:
        add_error('%r: returned %d' % (args, rv))


def mangle_name(name, mode, gitmode):
    """Mangle a file name to present an abstract name for segmented files.
    Mangled file names will have the ".bup" extension added to them. If a
    file's name already ends with ".bup", a ".bupl" extension is added to
    disambiguate normal files from semgmented ones.
    """
    if stat.S_ISREG(mode) and not stat.S_ISREG(gitmode):
        return name + '.bup'
    elif name.endswith('.bup') or name[:-1].endswith('.bup'):
        return name + '.bupl'
    else:
        return name


(BUP_NORMAL, BUP_CHUNKED) = (0,1)
def demangle_name(name):
    """Remove name mangling from a file name, if necessary.

    The return value is a tuple (demangled_filename,mode), where mode is one of
    the following:

    * BUP_NORMAL  : files that should be read as-is from the repository
    * BUP_CHUNKED : files that were chunked and need to be assembled

    For more information on the name mangling algorythm, see mangle_name()
    """
    if name.endswith('.bupl'):
        return (name[:-5], BUP_NORMAL)
    elif name.endswith('.bup'):
        return (name[:-4], BUP_CHUNKED)
    else:
        return (name, BUP_NORMAL)


def _encode_packobj(type, content):
    szout = ''
    sz = len(content)
    szbits = (sz & 0x0f) | (_typemap[type]<<4)
    sz >>= 4
    while 1:
        if sz: szbits |= 0x80
        szout += chr(szbits)
        if not sz:
            break
        szbits = sz & 0x7f
        sz >>= 7
    z = zlib.compressobj(1)
    yield szout
    yield z.compress(content)
    yield z.flush()


def _encode_looseobj(type, content):
    z = zlib.compressobj(1)
    yield z.compress('%s %d\0' % (type, len(content)))
    yield z.compress(content)
    yield z.flush()


def _decode_looseobj(buf):
    assert(buf);
    s = zlib.decompress(buf)
    i = s.find('\0')
    assert(i > 0)
    l = s[:i].split(' ')
    type = l[0]
    sz = int(l[1])
    content = s[i+1:]
    assert(type in _typemap)
    assert(sz == len(content))
    return (type, content)


def _decode_packobj(buf):
    assert(buf)
    c = ord(buf[0])
    type = _typermap[(c & 0x70) >> 4]
    sz = c & 0x0f
    shift = 4
    i = 0
    while c & 0x80:
        i += 1
        c = ord(buf[i])
        sz |= (c & 0x7f) << shift
        shift += 7
        if not (c & 0x80):
            break
    return (type, zlib.decompress(buf[i+1:]))


class PackIdx:
    def __init__(self):
        assert(0)

    def find_offset(self, hash):
        """Get the offset of an object inside the index file."""
        idx = self._idx_from_hash(hash)
        if idx != None:
            return self._ofs_from_idx(idx)
        return None

    def exists(self, hash, want_source=False):
        """Return nonempty if the object exists in this index."""
        if hash and (self._idx_from_hash(hash) != None):
            return want_source and self.name or True
        return None

    def __len__(self):
        return int(self.fanout[255])

    def _idx_from_hash(self, hash):
        global _total_searches, _total_steps
        _total_searches += 1
        assert(len(hash) == 20)
        b1 = ord(hash[0])
        start = self.fanout[b1-1] # range -1..254
        end = self.fanout[b1] # range 0..255
        want = str(hash)
        _total_steps += 1  # lookup table is a step
        while start < end:
            _total_steps += 1
            mid = start + (end-start)/2
            v = self._idx_to_hash(mid)
            if v < want:
                start = mid+1
            elif v > want:
                end = mid
            else: # got it!
                return mid
        return None


class PackIdxV1(PackIdx):
    """Object representation of a Git pack index (version 1) file."""
    def __init__(self, filename, f):
        self.name = filename
        self.idxnames = [self.name]
        self.map = mmap_read(f)
        self.fanout = list(struct.unpack('!256I',
                                         str(buffer(self.map, 0, 256*4))))
        self.fanout.append(0)  # entry "-1"
        nsha = self.fanout[255]
        self.sha_ofs = 256*4
        self.shatable = buffer(self.map, self.sha_ofs, nsha*24)

    def _ofs_from_idx(self, idx):
        return struct.unpack('!I', str(self.shatable[idx*24 : idx*24+4]))[0]

    def _idx_to_hash(self, idx):
        return str(self.shatable[idx*24+4 : idx*24+24])

    def __iter__(self):
        for i in xrange(self.fanout[255]):
            yield buffer(self.map, 256*4 + 24*i + 4, 20)


class PackIdxV2(PackIdx):
    """Object representation of a Git pack index (version 2) file."""
    def __init__(self, filename, f):
        self.name = filename
        self.idxnames = [self.name]
        self.map = mmap_read(f)
        assert(str(self.map[0:8]) == '\377tOc\0\0\0\2')
        self.fanout = list(struct.unpack('!256I',
                                         str(buffer(self.map, 8, 256*4))))
        self.fanout.append(0)  # entry "-1"
        nsha = self.fanout[255]
        self.sha_ofs = 8 + 256*4
        self.shatable = buffer(self.map, self.sha_ofs, nsha*20)
        self.ofstable = buffer(self.map,
                               self.sha_ofs + nsha*20 + nsha*4,
                               nsha*4)
        self.ofs64table = buffer(self.map,
                                 8 + 256*4 + nsha*20 + nsha*4 + nsha*4)

    def _ofs_from_idx(self, idx):
        ofs = struct.unpack('!I', str(buffer(self.ofstable, idx*4, 4)))[0]
        if ofs & 0x80000000:
            idx64 = ofs & 0x7fffffff
            ofs = struct.unpack('!Q',
                                str(buffer(self.ofs64table, idx64*8, 8)))[0]
        return ofs

    def _idx_to_hash(self, idx):
        return str(self.shatable[idx*20:(idx+1)*20])

    def __iter__(self):
        for i in xrange(self.fanout[255]):
            yield buffer(self.map, 8 + 256*4 + 20*i, 20)


extract_bits = _helpers.extract_bits

bloom_contains = _helpers.bloom_contains
bloom_add = _helpers.bloom_add


class ShaBloom:
    """Wrapper which contains data from multiple index files.
    Multiple index (.midx) files constitute a wrapper around index (.idx) files
    and make it possible for bup to expand Git's indexing capabilities to vast
    amounts of files.
    """
    def __init__(self, filename, f=None, readwrite=False):
        self.name = filename
        self.rwfile = None
        self.map = None
        assert(filename.endswith('.bloom'))
        if readwrite:
            self.rwfile = f or open(filename, 'r+b')
            self.map = mmap_readwrite(self.rwfile, close=False)
        else:
            self.rwfile = None
            self.map = mmap_read(f or open(filename, 'rb'))
        if str(self.map[0:4]) != 'BLOM':
            log('Warning: skipping: invalid BLOM header in %r\n' % filename)
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
            self.map.close()
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
        if self.map:
            if self.rwfile:
                debug2("bloom: closing with %d entries\n" % self.entries)
                self.map[12:16] = struct.pack('!I', self.entries)
                self.map.flush()
        if self.rwfile:
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
        if not self.map: raise Exception, "Cannot add to closed bloom"
        self.entries += bloom_add(self.map, ix.shatable, self.bits, self.k)
        self.idxnames.append(os.path.basename(ix.name))

    def exists(self, sha):
        """Return nonempty if the object probably exists in the bloom filter."""
        global _total_searches, _total_steps
        _total_searches += 1
        if not self.map: return None
        found, steps = bloom_contains(self.map, str(sha), self.bits, self.k)
        _total_steps += steps
        return found

    @classmethod
    def create(cls, name, f=None, readwrite=False, expected=100000, k=None):
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
        f.write('\0'*2**bits)
        f.seek(0)
        return cls(name, f=f, readwrite=readwrite)

    def __len__(self):
        return self.entries


class PackMidx:
    """Wrapper which contains data from multiple index files.
    Multiple index (.midx) files constitute a wrapper around index (.idx) files
    and make it possible for bup to expand Git's indexing capabilities to vast
    amounts of files.
    """
    def __init__(self, filename):
        self.name = filename
        self.force_keep = False
        assert(filename.endswith('.midx'))
        self.map = mmap_read(open(filename))
        if str(self.map[0:4]) != 'MIDX':
            log('Warning: skipping: invalid MIDX header in %r\n' % filename)
            self.force_keep = True
            return self._init_failed()
        ver = struct.unpack('!I', self.map[4:8])[0]
        if ver < MIDX_VERSION:
            log('Warning: ignoring old-style (v%d) midx %r\n' 
                % (ver, filename))
            self.force_keep = False  # old stuff is boring  
            return self._init_failed()
        if ver > MIDX_VERSION:
            log('Warning: ignoring too-new (v%d) midx %r\n'
                % (ver, filename))
            self.force_keep = True  # new stuff is exciting
            return self._init_failed()

        self.bits = _helpers.firstword(self.map[8:12])
        self.entries = 2**self.bits
        self.fanout = buffer(self.map, 12, self.entries*4)
        self.sha_ofs = 12 + self.entries*4
        self.nsha = nsha = self._fanget(self.entries-1)
        self.shatable = buffer(self.map, self.sha_ofs, nsha*20)
        self.whichlist = buffer(self.map, self.sha_ofs + nsha*20, nsha*4)
        self.idxname_ofs = self.sha_ofs + 24*nsha
        self.idxnames = str(self.map[self.idxname_ofs:]).split('\0')

    def _init_failed(self):
        self.bits = 0
        self.entries = 1
        self.fanout = buffer('\0\0\0\0')
        self.shatable = buffer('\0'*20)
        self.idxnames = []

    def _fanget(self, i):
        start = i*4
        s = self.fanout[start:start+4]
        return _helpers.firstword(s)

    def _get(self, i):
        return str(self.shatable[i*20:(i+1)*20])

    def _get_idx_i(self, i):
        return struct.unpack('!I', self.whichlist[i*4:(i+1)*4])[0]

    def _get_idxname(self, i):
        return self.idxnames[self._get_idx_i(i)]

    def exists(self, hash, want_source=False):
        """Return nonempty if the object exists in the index files."""
        global _total_searches, _total_steps
        _total_searches += 1
        want = str(hash)
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
            mid = start + (hashv-startv)*(end-start-1)/(endv-startv)
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
        for i in xrange(self._fanget(self.entries-1)):
            yield buffer(self.shatable, i*20, 20)

    def __len__(self):
        return int(self._fanget(self.entries-1))


_mpi_count = 0
class PackIdxList:
    def __init__(self, dir):
        global _mpi_count
        assert(_mpi_count == 0) # these things suck tons of VM; don't waste it
        _mpi_count += 1
        self.dir = dir
        self.also = set()
        self.packs = []
        self.do_bloom = False
        self.bloom = None
        self.refresh()

    def __del__(self):
        global _mpi_count
        _mpi_count -= 1
        assert(_mpi_count == 0)

    def __iter__(self):
        return iter(idxmerge(self.packs))

    def __len__(self):
        return sum(len(pack) for pack in self.packs)

    def exists(self, hash, want_source=False):
        """Return nonempty if the object exists in the index files."""
        global _total_searches
        _total_searches += 1
        if hash in self.also:
            return True
        if self.do_bloom and self.bloom is not None:
            _total_searches -= 1  # will be incremented by bloom
            if self.bloom.exists(hash):
                self.do_bloom = False
            else:
                return None
        for i in xrange(len(self.packs)):
            p = self.packs[i]
            _total_searches -= 1  # will be incremented by sub-pack
            ix = p.exists(hash, want_source=want_source)
            if ix:
                # reorder so most recently used packs are searched first
                self.packs = [p] + self.packs[:i] + self.packs[i+1:]
                return ix
        self.do_bloom = True
        return None

    def refresh(self, skip_midx = False):
        """Refresh the index list.
        This method verifies if .midx files were superseded (e.g. all of its
        contents are in another, bigger .midx file) and removes the superseded
        files.

        If skip_midx is True, all work on .midx files will be skipped and .midx
        files will be removed from the list.

        The module-global variable 'ignore_midx' can force this function to
        always act as if skip_midx was True.
        """
        self.bloom = None # Always reopen the bloom as it may have been relaced
        self.do_bloom = False
        skip_midx = skip_midx or ignore_midx
        d = dict((p.name, p) for p in self.packs
                 if not skip_midx or not isinstance(p, PackMidx))
        if os.path.exists(self.dir):
            if not skip_midx:
                midxl = []
                for ix in self.packs:
                    if isinstance(ix, PackMidx):
                        for name in ix.idxnames:
                            d[os.path.join(self.dir, name)] = ix
                for full in glob.glob(os.path.join(self.dir,'*.midx')):
                    if not d.get(full):
                        mx = PackMidx(full)
                        (mxd, mxf) = os.path.split(mx.name)
                        broken = False
                        for n in mx.idxnames:
                            if not os.path.exists(os.path.join(mxd, n)):
                                log(('warning: index %s missing\n' +
                                    '  used by %s\n') % (n, mxf))
                                broken = True
                        if broken:
                            del mx
                            unlink(full)
                        else:
                            midxl.append(mx)
                midxl.sort(lambda x,y: -cmp(len(x),len(y)))
                for ix in midxl:
                    any_needed = False
                    for sub in ix.idxnames:
                        found = d.get(os.path.join(self.dir, sub))
                        if not found or isinstance(found, PackIdx):
                            # doesn't exist, or exists but not in a midx
                            any_needed = True
                            break
                    if any_needed:
                        d[ix.name] = ix
                        for name in ix.idxnames:
                            d[os.path.join(self.dir, name)] = ix
                    elif not ix.force_keep:
                        debug1('midx: removing redundant: %s\n'
                               % os.path.basename(ix.name))
                        unlink(ix.name)
            for full in glob.glob(os.path.join(self.dir,'*.idx')):
                if not d.get(full):
                    try:
                        ix = open_idx(full)
                    except GitError, e:
                        add_error(e)
                        continue
                    d[full] = ix
            bfull = os.path.join(self.dir, 'bup.bloom')
            if self.bloom is None and os.path.exists(bfull):
                self.bloom = ShaBloom(bfull)
            self.packs = list(set(d.values()))
            self.packs.sort(lambda x,y: -cmp(len(x),len(y)))
            if self.bloom and self.bloom.valid() and len(self.bloom) >= len(self):
                self.do_bloom = True
            else:
                self.bloom = None
        debug1('PackIdxList: using %d index%s.\n'
            % (len(self.packs), len(self.packs)!=1 and 'es' or ''))

    def add(self, hash):
        """Insert an additional object in the list."""
        self.also.add(hash)


def calc_hash(type, content):
    """Calculate some content's hash in the Git fashion."""
    header = '%s %d\0' % (type, len(content))
    sum = Sha1(header)
    sum.update(content)
    return sum.digest()


def _shalist_sort_key(ent):
    (mode, name, id) = ent
    if stat.S_ISDIR(int(mode, 8)):
        return name + '/'
    else:
        return name


def open_idx(filename):
    if filename.endswith('.idx'):
        f = open(filename, 'rb')
        header = f.read(8)
        if header[0:4] == '\377tOc':
            version = struct.unpack('!I', header[4:8])[0]
            if version == 2:
                return PackIdxV2(filename, f)
            else:
                raise GitError('%s: expected idx file version 2, got %d'
                               % (filename, version))
        elif len(header) == 8 and header[0:4] < '\377tOc':
            return PackIdxV1(filename, f)
        else:
            raise GitError('%s: unrecognized idx file header' % filename)
    elif filename.endswith('.midx'):
        return PackMidx(filename)
    else:
        raise GitError('idx filenames must end with .idx or .midx')


def idxmerge(idxlist, final_progress=True):
    """Generate a list of all the objects reachable in a PackIdxList."""
    def pfunc(count, total):
        progress('Reading indexes: %.2f%% (%d/%d)\r'
                 % (count*100.0/total, count, total))
    def pfinal(count, total):
        if final_progress:
            log('Reading indexes: %.2f%% (%d/%d), done.\n' % (100, total, total))
    return merge_iter(idxlist, 10024, pfunc, pfinal)


def _make_objcache():
    return PackIdxList(repo('objects/pack'))

class PackWriter:
    """Writes Git objects insid a pack file."""
    def __init__(self, objcache_maker=_make_objcache):
        self.count = 0
        self.outbytes = 0
        self.filename = None
        self.file = None
        self.idx = None
        self.objcache_maker = objcache_maker
        self.objcache = None

    def __del__(self):
        self.close()

    def _open(self):
        if not self.file:
            (fd,name) = tempfile.mkstemp(suffix='.pack', dir=repo('objects'))
            self.file = os.fdopen(fd, 'w+b')
            assert(name.endswith('.pack'))
            self.filename = name[:-5]
            self.file.write('PACK\0\0\0\2\0\0\0\0')
            self.idx = list(list() for i in xrange(256))

    # the 'sha' parameter is used in client.py's _raw_write(), but not needed
    # in this basic version.
    def _raw_write(self, datalist, sha):
        self._open()
        f = self.file
        # in case we get interrupted (eg. KeyboardInterrupt), it's best if
        # the file never has a *partial* blob.  So let's make sure it's
        # all-or-nothing.  (The blob shouldn't be very big anyway, thanks
        # to our hashsplit algorithm.)  f.write() does its own buffering,
        # but that's okay because we'll flush it in _end().
        oneblob = ''.join(datalist)
        try:
            f.write(oneblob)
        except IOError, e:
            raise GitError, e, sys.exc_info()[2]
        nw = len(oneblob)
        crc = zlib.crc32(oneblob) & 0xffffffff
        self._update_idx(sha, crc, nw)
        self.outbytes += nw
        self.count += 1
        return nw, crc

    def _update_idx(self, sha, crc, size):
        assert(sha)
        if self.idx:
            self.idx[ord(sha[0])].append((sha, crc, self.file.tell() - size))

    def _write(self, sha, type, content):
        if verbose:
            log('>')
        if not sha:
            sha = calc_hash(type, content)
        size, crc = self._raw_write(_encode_packobj(type, content), sha=sha)
        return sha

    def breakpoint(self):
        """Clear byte and object counts and return the last processed id."""
        id = self._end()
        self.outbytes = self.count = 0
        return id

    def _require_objcache(self):
        if self.objcache is None and self.objcache_maker:
            self.objcache = self.objcache_maker()
        if self.objcache is None:
            raise GitError(
                    "PackWriter not opened or can't check exists w/o objcache")

    def exists(self, id, want_source=False):
        """Return non-empty if an object is found in the object cache."""
        self._require_objcache()
        return self.objcache.exists(id, want_source=want_source)

    def maybe_write(self, type, content):
        """Write an object to the pack file if not present and return its id."""
        self._require_objcache()
        sha = calc_hash(type, content)
        if not self.exists(sha):
            self._write(sha, type, content)
            self.objcache.add(sha)
        return sha

    def new_blob(self, blob):
        """Create a blob object in the pack with the supplied content."""
        return self.maybe_write('blob', blob)

    def new_tree(self, shalist):
        """Create a tree object in the pack."""
        shalist = sorted(shalist, key = _shalist_sort_key)
        l = []
        for (mode,name,bin) in shalist:
            assert(mode)
            assert(mode != '0')
            assert(mode[0] != '0')
            assert(name)
            assert(len(bin) == 20)
            l.append('%s %s\0%s' % (mode,name,bin))
        return self.maybe_write('tree', ''.join(l))

    def _new_commit(self, tree, parent, author, adate, committer, cdate, msg):
        l = []
        if tree: l.append('tree %s' % tree.encode('hex'))
        if parent: l.append('parent %s' % parent.encode('hex'))
        if author: l.append('author %s %s' % (author, _git_date(adate)))
        if committer: l.append('committer %s %s' % (committer, _git_date(cdate)))
        l.append('')
        l.append(msg)
        return self.maybe_write('commit', '\n'.join(l))

    def new_commit(self, parent, tree, date, msg):
        """Create a commit object in the pack."""
        userline = '%s <%s@%s>' % (userfullname(), username(), hostname())
        commit = self._new_commit(tree, parent,
                                  userline, date, userline, date,
                                  msg)
        return commit

    def abort(self):
        """Remove the pack file from disk."""
        f = self.file
        if f:
            self.idx = None
            self.file = None
            f.close()
            os.unlink(self.filename + '.pack')

    def _end(self, run_midx=True):
        f = self.file
        if not f: return None
        self.file = None
        self.objcache = None
        idx = self.idx
        self.idx = None

        # update object count
        f.seek(8)
        cp = struct.pack('!i', self.count)
        assert(len(cp) == 4)
        f.write(cp)

        # calculate the pack sha1sum
        f.seek(0)
        sum = Sha1()
        for b in chunkyreader(f):
            sum.update(b)
        packbin = sum.digest()
        f.write(packbin)
        f.close()

        idx_f = open(self.filename + '.idx', 'wb')
        obj_list_sha = self._write_pack_idx_v2(idx_f, idx, packbin)
        idx_f.close()

        nameprefix = repo('objects/pack/pack-%s' % obj_list_sha)
        if os.path.exists(self.filename + '.map'):
            os.unlink(self.filename + '.map')
        os.rename(self.filename + '.pack', nameprefix + '.pack')
        os.rename(self.filename + '.idx', nameprefix + '.idx')

        if run_midx:
            auto_midx(repo('objects/pack'))
        return nameprefix

    def close(self, run_midx=True):
        """Close the pack file and move it to its definitive path."""
        return self._end(run_midx=run_midx)

    def _write_pack_idx_v2(self, file, idx, packbin):
        sum = Sha1()

        def write(data):
            file.write(data)
            sum.update(data)

        write('\377tOc\0\0\0\2')

        n = 0
        for part in idx:
            n += len(part)
            write(struct.pack('!i', n))
            part.sort(key=lambda x: x[0])

        obj_list_sum = Sha1()
        for part in idx:
            for entry in part:
                write(entry[0])
                obj_list_sum.update(entry[0])
        for part in idx:
            for entry in part:
                write(struct.pack('!I', entry[1]))
        ofs64_list = []
        for part in idx:
            for entry in part:
                if entry[2] & 0x80000000:
                    write(struct.pack('!I', 0x80000000 | len(ofs64_list)))
                    ofs64_list.append(struct.pack('!Q', entry[2]))
                else:
                    write(struct.pack('!i', entry[2]))
        for ofs64 in ofs64_list:
            write(ofs64)

        write(packbin)
        file.write(sum.digest())
        return obj_list_sum.hexdigest()


def _git_date(date):
    return '%d %s' % (date, time.strftime('%z', time.localtime(date)))


def _gitenv():
    os.environ['GIT_DIR'] = os.path.abspath(repo())


def list_refs(refname = None):
    """Generate a list of tuples in the form (refname,hash).
    If a ref name is specified, list only this particular ref.
    """
    argv = ['git', 'show-ref', '--']
    if refname:
        argv += [refname]
    p = subprocess.Popen(argv, preexec_fn = _gitenv, stdout = subprocess.PIPE)
    out = p.stdout.read().strip()
    rv = p.wait()  # not fatal
    if rv:
        assert(not out)
    if out:
        for d in out.split('\n'):
            (sha, name) = d.split(' ', 1)
            yield (name, sha.decode('hex'))


def read_ref(refname):
    """Get the commit id of the most recent commit made on a given ref."""
    l = list(list_refs(refname))
    if l:
        assert(len(l) == 1)
        return l[0][1]
    else:
        return None


def rev_list(ref, count=None):
    """Generate a list of reachable commits in reverse chronological order.

    This generator walks through commits, from child to parent, that are
    reachable via the specified ref and yields a series of tuples of the form
    (date,hash).

    If count is a non-zero integer, limit the number of commits to "count"
    objects.
    """
    assert(not ref.startswith('-'))
    opts = []
    if count:
        opts += ['-n', str(atoi(count))]
    argv = ['git', 'rev-list', '--pretty=format:%ct'] + opts + [ref, '--']
    p = subprocess.Popen(argv, preexec_fn = _gitenv, stdout = subprocess.PIPE)
    commit = None
    for row in p.stdout:
        s = row.strip()
        if s.startswith('commit '):
            commit = s[7:].decode('hex')
        else:
            date = int(s)
            yield (date, commit)
    rv = p.wait()  # not fatal
    if rv:
        raise GitError, 'git rev-list returned error %d' % rv


def rev_get_date(ref):
    """Get the date of the latest commit on the specified ref."""
    for (date, commit) in rev_list(ref, count=1):
        return date
    raise GitError, 'no such commit %r' % ref


def rev_parse(committish):
    """Resolve the full hash for 'committish', if it exists.

    Should be roughly equivalent to 'git rev-parse'.

    Returns the hex value of the hash if it is found, None if 'committish' does
    not correspond to anything.
    """
    head = read_ref(committish)
    if head:
        debug2("resolved from ref: commit = %s\n" % head.encode('hex'))
        return head

    pL = PackIdxList(repo('objects/pack'))

    if len(committish) == 40:
        try:
            hash = committish.decode('hex')
        except TypeError:
            return None

        if pL.exists(hash):
            return hash

    return None


def update_ref(refname, newval, oldval):
    """Change the commit pointed to by a branch."""
    if not oldval:
        oldval = ''
    assert(refname.startswith('refs/heads/'))
    p = subprocess.Popen(['git', 'update-ref', refname,
                          newval.encode('hex'), oldval.encode('hex')],
                         preexec_fn = _gitenv)
    _git_wait('git update-ref', p)


def guess_repo(path=None):
    """Set the path value in the global variable "repodir".
    This makes bup look for an existing bup repository, but not fail if a
    repository doesn't exist. Usually, if you are interacting with a bup
    repository, you would not be calling this function but using
    check_repo_or_die().
    """
    global repodir
    if path:
        repodir = path
    if not repodir:
        repodir = os.environ.get('BUP_DIR')
        if not repodir:
            repodir = os.path.expanduser('~/.bup')


def init_repo(path=None):
    """Create the Git bare repository for bup in a given path."""
    guess_repo(path)
    d = repo()  # appends a / to the path
    parent = os.path.dirname(os.path.dirname(d))
    if parent and not os.path.exists(parent):
        raise GitError('parent directory "%s" does not exist\n' % parent)
    if os.path.exists(d) and not os.path.isdir(os.path.join(d, '.')):
        raise GitError('"%d" exists but is not a directory\n' % d)
    p = subprocess.Popen(['git', '--bare', 'init'], stdout=sys.stderr,
                         preexec_fn = _gitenv)
    _git_wait('git init', p)
    # Force the index version configuration in order to ensure bup works
    # regardless of the version of the installed Git binary.
    p = subprocess.Popen(['git', 'config', 'pack.indexVersion', '2'],
                         stdout=sys.stderr, preexec_fn = _gitenv)
    _git_wait('git config', p)


def check_repo_or_die(path=None):
    """Make sure a bup repository exists, and abort if not.
    If the path to a particular repository was not specified, this function
    initializes the default repository automatically.
    """
    guess_repo(path)
    if not os.path.isdir(repo('objects/pack/.')):
        if repodir == home_repodir:
            init_repo()
        else:
            log('error: %r is not a bup/git repository\n' % repo())
            sys.exit(15)


def treeparse(buf):
    """Generate a list of (mode, name, hash) tuples of objects from 'buf'."""
    ofs = 0
    while ofs < len(buf):
        z = buf[ofs:].find('\0')
        assert(z > 0)
        spl = buf[ofs:ofs+z].split(' ', 1)
        assert(len(spl) == 2)
        sha = buf[ofs+z+1:ofs+z+1+20]
        ofs += z+1+20
        yield (spl[0], spl[1], sha)


_ver = None
def ver():
    """Get Git's version and ensure a usable version is installed.

    The returned version is formatted as an ordered tuple with each position
    representing a digit in the version tag. For example, the following tuple
    would represent version 1.6.6.9:

        ('1', '6', '6', '9')
    """
    global _ver
    if not _ver:
        p = subprocess.Popen(['git', '--version'],
                             stdout=subprocess.PIPE)
        gvs = p.stdout.read()
        _git_wait('git --version', p)
        m = re.match(r'git version (\S+.\S+)', gvs)
        if not m:
            raise GitError('git --version weird output: %r' % gvs)
        _ver = tuple(m.group(1).split('.'))
    needed = ('1','5', '3', '1')
    if _ver < needed:
        raise GitError('git version %s or higher is required; you have %s'
                       % ('.'.join(needed), '.'.join(_ver)))
    return _ver


def _git_wait(cmd, p):
    rv = p.wait()
    if rv != 0:
        raise GitError('%s returned %d' % (cmd, rv))


def _git_capture(argv):
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, preexec_fn = _gitenv)
    r = p.stdout.read()
    _git_wait(repr(argv), p)
    return r


class _AbortableIter:
    def __init__(self, it, onabort = None):
        self.it = it
        self.onabort = onabort
        self.done = None

    def __iter__(self):
        return self

    def next(self):
        try:
            return self.it.next()
        except StopIteration, e:
            self.done = True
            raise
        except:
            self.abort()
            raise

    def abort(self):
        """Abort iteration and call the abortion callback, if needed."""
        if not self.done:
            self.done = True
            if self.onabort:
                self.onabort()

    def __del__(self):
        self.abort()


_ver_warned = 0
class CatPipe:
    """Link to 'git cat-file' that is used to retrieve blob data."""
    def __init__(self):
        global _ver_warned
        wanted = ('1','5','6')
        if ver() < wanted:
            if not _ver_warned:
                log('warning: git version < %s; bup will be slow.\n'
                    % '.'.join(wanted))
                _ver_warned = 1
            self.get = self._slow_get
        else:
            self.p = self.inprogress = None
            self.get = self._fast_get

    def _abort(self):
        if self.p:
            self.p.stdout.close()
            self.p.stdin.close()
        self.p = None
        self.inprogress = None

    def _restart(self):
        self._abort()
        self.p = subprocess.Popen(['git', 'cat-file', '--batch'],
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  close_fds = True,
                                  bufsize = 4096,
                                  preexec_fn = _gitenv)

    def _fast_get(self, id):
        if not self.p or self.p.poll() != None:
            self._restart()
        assert(self.p)
        assert(self.p.poll() == None)
        if self.inprogress:
            log('_fast_get: opening %r while %r is open'
                % (id, self.inprogress))
        assert(not self.inprogress)
        assert(id.find('\n') < 0)
        assert(id.find('\r') < 0)
        assert(not id.startswith('-'))
        self.inprogress = id
        self.p.stdin.write('%s\n' % id)
        self.p.stdin.flush()
        hdr = self.p.stdout.readline()
        if hdr.endswith(' missing\n'):
            self.inprogress = None
            raise KeyError('blob %r is missing' % id)
        spl = hdr.split(' ')
        if len(spl) != 3 or len(spl[0]) != 40:
            raise GitError('expected blob, got %r' % spl)
        (hex, type, size) = spl

        it = _AbortableIter(chunkyreader(self.p.stdout, int(spl[2])),
                           onabort = self._abort)
        try:
            yield type
            for blob in it:
                yield blob
            assert(self.p.stdout.readline() == '\n')
            self.inprogress = None
        except Exception, e:
            it.abort()
            raise

    def _slow_get(self, id):
        assert(id.find('\n') < 0)
        assert(id.find('\r') < 0)
        assert(id[0] != '-')
        type = _git_capture(['git', 'cat-file', '-t', id]).strip()
        yield type

        p = subprocess.Popen(['git', 'cat-file', type, id],
                             stdout=subprocess.PIPE,
                             preexec_fn = _gitenv)
        for blob in chunkyreader(p.stdout):
            yield blob
        _git_wait('git cat-file', p)

    def _join(self, it):
        type = it.next()
        if type == 'blob':
            for blob in it:
                yield blob
        elif type == 'tree':
            treefile = ''.join(it)
            for (mode, name, sha) in treeparse(treefile):
                for blob in self.join(sha.encode('hex')):
                    yield blob
        elif type == 'commit':
            treeline = ''.join(it).split('\n')[0]
            assert(treeline.startswith('tree '))
            for blob in self.join(treeline[5:]):
                yield blob
        else:
            raise GitError('invalid object type %r: expected blob/tree/commit'
                           % type)

    def join(self, id):
        """Generate a list of the content of all blobs that can be reached
        from an object.  The hash given in 'id' must point to a blob, a tree
        or a commit. The content of all blobs that can be seen from trees or
        commits will be added to the list.
        """
        try:
            for d in self._join(self.get(id)):
                yield d
        except StopIteration:
            log('booger!\n')

def tags():
    """Return a dictionary of all tags in the form {hash: [tag_names, ...]}."""
    tags = {}
    for (n,c) in list_refs():
        if n.startswith('refs/tags/'):
            name = n[10:]
            if not c in tags:
                tags[c] = []

            tags[c].append(name)  # more than one tag can point at 'c'

    return tags
