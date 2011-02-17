import math
from bup import _helpers
from bup.helpers import *

BLOB_MAX = 8192*2   # 8192 is the "typical" blob size for bupsplit
BLOB_READ_SIZE = 1024*1024
MAX_PER_TREE = 256
progress_callback = None
max_pack_size = 1000*1000*1000  # larger packs will slow down pruning
max_pack_objects = 200*1000  # cache memory usage is about 83 bytes per object
fanout = 16

# The purpose of this type of buffer is to avoid copying on peek(), get(),
# and eat().  We do copy the buffer contents on put(), but that should
# be ok if we always only put() large amounts of data at a time.
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


def readfile_iter(files, progress=None):
    for filenum,f in enumerate(files):
        ofs = 0
        b = ''
        while 1:
            if progress:
                progress(filenum, len(b))
            fadvise_done(f, max(0, ofs - 1024*1024))
            b = f.read(BLOB_READ_SIZE)
            ofs += len(b)
            if not b:
                fadvise_done(f, ofs)
                break
            yield b


def _splitbuf(buf):
    while 1:
        b = buf.peek(buf.used())
        (ofs, bits) = _helpers.splitbuf(b)
        if ofs:
            buf.eat(ofs)
            yield buffer(b, 0, ofs), bits
        else:
            break
    if buf.used() > BLOB_MAX:
        # limit max blob size
        yield buf.get(BLOB_MAX), 0


def _hashsplit_iter(files, progress):
    assert(BLOB_READ_SIZE > BLOB_MAX)
    buf = Buf()
    for inblock in readfile_iter(files, progress):
        buf.put(inblock)
        for buf_and_bits in _splitbuf(buf):
            yield buf_and_bits
    if buf.used():
        yield buf.get(buf.used()), 0


def _hashsplit_iter_keep_boundaries(files, progress):
    for real_filenum,f in enumerate(files):
        if progress:
            def prog(filenum, nbytes):
                # the inner _hashsplit_iter doesn't know the real file count,
                # so we'll replace it here.
                return progress(real_filenum, nbytes)
        else:
            prog = None
        for buf_and_bits in _hashsplit_iter([f], progress=prog):
            yield buf_and_bits


def hashsplit_iter(files, keep_boundaries, progress):
    if keep_boundaries:
        return _hashsplit_iter_keep_boundaries(files, progress)
    else:
        return _hashsplit_iter(files, progress)


total_split = 0
def _split_to_blobs(w, files, keep_boundaries, progress):
    global total_split
    for (blob, bits) in hashsplit_iter(files, keep_boundaries, progress):
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


def split_to_shalist(w, files, keep_boundaries, progress=None):
    sl = _split_to_blobs(w, files, keep_boundaries, progress)
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
