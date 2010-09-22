import math
from bup import _helpers
from bup.helpers import *

BLOB_LWM = 8192*2
BLOB_MAX = BLOB_LWM*2
BLOB_HWM = 1024*1024
MAX_PER_TREE = 256
progress_callback = None
max_pack_size = 1000*1000*1000  # larger packs will slow down pruning
max_pack_objects = 200*1000  # cache memory usage is about 83 bytes per object
fanout = 16

class Buf:
    def __init__(self):
        self.data = ''
        self.start = 0

    def put(self, s):
        if s:
            self.data = buffer(self.data, self.start) + s
            self.start = 0
            
    def peek(self, count):
        return buffer(self.data, self.start, count)
    
    def eat(self, count):
        self.start += count

    def get(self, count):
        v = buffer(self.data, self.start, count)
        self.start += count
        return v

    def used(self):
        return len(self.data) - self.start


def splitbuf(buf):
    b = buf.peek(buf.used())
    (ofs, bits) = _helpers.splitbuf(b)
    if ofs:
        buf.eat(ofs)
        return (buffer(b, 0, ofs), bits)
    return (None, 0)


def blobiter(files):
    for f in files:
        ofs = 0
        while 1:
            fadvise_done(f, max(0, ofs - 1024*1024))
            b = f.read(BLOB_HWM)
            ofs += len(b)
            if not b:
                fadvise_done(f, ofs)
                break
            yield b


def drainbuf(buf, finalize):
    while 1:
        (blob, bits) = splitbuf(buf)
        if blob:
            yield (blob, bits)
        else:
            break
    if buf.used() > BLOB_MAX:
        # limit max blob size
        yield (buf.get(buf.used()), 0)
    elif finalize and buf.used():
        yield (buf.get(buf.used()), 0)


def _hashsplit_iter(files):
    assert(BLOB_HWM > BLOB_MAX)
    buf = Buf()
    fi = blobiter(files)
    while 1:
        for i in drainbuf(buf, finalize=False):
            yield i
        while buf.used() < BLOB_HWM:
            bnew = next(fi)
            if not bnew:
                # eof
                for i in drainbuf(buf, finalize=True):
                    yield i
                return
            buf.put(bnew)


def _hashsplit_iter_keep_boundaries(files):
    for f in files:
        for i in _hashsplit_iter([f]):
            yield i


def hashsplit_iter(files, keep_boundaries):
    if keep_boundaries:
        return _hashsplit_iter_keep_boundaries(files)
    else:
        return _hashsplit_iter(files)


total_split = 0
def _split_to_blobs(w, files, keep_boundaries):
    global total_split
    for (blob, bits) in hashsplit_iter(files, keep_boundaries):
        sha = w.new_blob(blob)
        total_split += len(blob)
        if w.outbytes >= max_pack_size or w.count >= max_pack_objects:
            w.breakpoint()
        if progress_callback:
            progress_callback(len(blob))
        yield (sha, len(blob), bits)


def _make_shalist(l):
    ofs = 0
    shalist = []
    for (mode, sha, size) in l:
        shalist.append((mode, '%016x' % ofs, sha))
        ofs += size
    total = ofs
    return (shalist, total)


def _squish(w, stacks, n):
    i = 0
    while i<n or len(stacks[i]) > MAX_PER_TREE:
        while len(stacks) <= i+1:
            stacks.append([])
        if len(stacks[i]) == 1:
            stacks[i+1] += stacks[i]
        elif stacks[i]:
            (shalist, size) = _make_shalist(stacks[i])
            tree = w.new_tree(shalist)
            stacks[i+1].append(('40000', tree, size))
        stacks[i] = []
        i += 1


def split_to_shalist(w, files, keep_boundaries):
    sl = _split_to_blobs(w, files, keep_boundaries)
    if not fanout:
        shal = []
        for (sha,size,bits) in sl:
            shal.append(('100644', sha, size))
        return _make_shalist(shal)[0]
    else:
        base_bits = _helpers.blobbits()
        fanout_bits = int(math.log(fanout, 2))
        def bits_to_idx(n):
            assert(n >= base_bits)
            return (n - base_bits)/fanout_bits
        stacks = [[]]
        for (sha,size,bits) in sl:
            assert(bits <= 32)
            stacks[0].append(('100644', sha, size))
            if bits > base_bits:
                _squish(w, stacks, bits_to_idx(bits))
        #log('stacks: %r\n' % [len(i) for i in stacks])
        _squish(w, stacks, len(stacks)-1)
        #log('stacks: %r\n' % [len(i) for i in stacks])
        return _make_shalist(stacks[-1])[0]


def split_to_blob_or_tree(w, files, keep_boundaries):
    shalist = list(split_to_shalist(w, files, keep_boundaries))
    if len(shalist) == 1:
        return (shalist[0][0], shalist[0][2])
    elif len(shalist) == 0:
        return ('100644', w.new_blob(''))
    else:
        return ('40000', w.new_tree(shalist))


def open_noatime(name):
    fd = _helpers.open_noatime(name)
    try:
        return os.fdopen(fd, 'rb', 1024*1024)
    except:
        try:
            os.close(fd)
        except:
            pass
        raise


def fadvise_done(f, ofs):
    assert(ofs >= 0)
    if ofs > 0 and hasattr(f, 'fileno'):
        _helpers.fadvise_done(f.fileno(), ofs)
