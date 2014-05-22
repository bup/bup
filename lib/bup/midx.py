import mmap
from bup import _helpers
from bup.helpers import *

MIDX_VERSION = 4

extract_bits = _helpers.extract_bits
_total_searches = 0
_total_steps = 0


class PackMidx:
    """Wrapper which contains data from multiple index files.
    Multiple index (.midx) files constitute a wrapper around index (.idx) files
    and make it possible for bup to expand Git's indexing capabilities to vast
    amounts of files.
    """
    def __init__(self, filename):
        self.name = filename
        self.force_keep = False
        self.map = None
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
        self.which_ofs = self.sha_ofs + 20*nsha
        self.whichlist = buffer(self.map, self.which_ofs, nsha*4)
        self.idxnames = str(self.map[self.which_ofs + 4*nsha:]).split('\0')

    def __del__(self):
        self.close()

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

    def close(self):
        if self.map is not None:
            self.map.close()
            self.map = None

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


