
from __future__ import absolute_import
import io, math, os

from bup import _helpers, compat, helpers
from bup._helpers import cat_bytes
from bup.compat import buffer, py_maj
from bup.helpers import sc_page_size


_fmincore = getattr(helpers, 'fmincore', None)

BLOB_MAX = 8192*4   # 8192 is the "typical" blob size for bupsplit
BLOB_READ_SIZE = 1024*1024
MAX_PER_TREE = 256
progress_callback = None
fanout = 16

GIT_MODE_FILE = 0o100644
GIT_MODE_TREE = 0o40000
GIT_MODE_SYMLINK = 0o120000

# The purpose of this type of buffer is to avoid copying on peek(), get(),
# and eat().  We do copy the buffer contents on put(), but that should
# be ok if we always only put() large amounts of data at a time.
class Buf:
    def __init__(self):
        self.data = b''
        self.start = 0

    def put(self, s):
        if not self.data:
            self.data = s
            self.start = 0
        elif s:
            remaining = len(self.data) - self.start
            self.data = cat_bytes(self.data, self.start, remaining,
                                  s, 0, len(s))
            self.start = 0
            
    def peek(self, count):
        if count <= 256:
            return self.data[self.start : self.start + count]
        return buffer(self.data, self.start, count)
    
    def eat(self, count):
        self.start += count

    def get(self, count):
        if count <= 256:
            v = self.data[self.start : self.start + count]
        else:
            v = buffer(self.data, self.start, count)
        self.start += count
        return v

    def used(self):
        return len(self.data) - self.start


def _fadvise_pages_done(fd, first_page, count):
    assert(first_page >= 0)
    assert(count >= 0)
    if count > 0:
        _helpers.fadvise_done(fd,
                              first_page * sc_page_size,
                              count * sc_page_size)


def _nonresident_page_regions(status_bytes, incore_mask, max_region_len=None):
    """Return (start_page, count) pairs in ascending start_page order for
    each contiguous region of nonresident pages indicated by the
    mincore() status_bytes.  Limit the number of pages in each region
    to max_region_len."""
    assert(max_region_len is None or max_region_len > 0)
    start = None
    for i, x in enumerate(status_bytes):
        in_core = x & incore_mask
        if start is None:
            if not in_core:
                start = i
        else:
            count = i - start
            if in_core:
                yield (start, count)
                start = None
            elif max_region_len and count >= max_region_len:
                yield (start, count)
                start = i
    if start is not None:
        yield (start, len(status_bytes) - start)


def _uncache_ours_upto(fd, offset, first_region, remaining_regions):
    """Uncache the pages of fd indicated by first_region and
    remaining_regions that are before offset, where each region is a
    (start_page, count) pair.  The final region must have a start_page
    of None."""
    rstart, rlen = first_region
    while rstart is not None and (rstart + rlen) * sc_page_size <= offset:
        _fadvise_pages_done(fd, rstart, rlen)
        rstart, rlen = next(remaining_regions, (None, None))
    return (rstart, rlen)


def readfile_iter(files, progress=None):
    for filenum,f in enumerate(files):
        ofs = 0
        b = ''
        fd = rpr = rstart = rlen = None
        if _fmincore and hasattr(f, 'fileno'):
            try:
                fd = f.fileno()
            except io.UnsupportedOperation:
                pass
            if fd:
                mcore = _fmincore(fd)
                if mcore:
                    max_chunk = max(1, (8 * 1024 * 1024) / sc_page_size)
                    rpr = _nonresident_page_regions(mcore, helpers.MINCORE_INCORE,
                                                    max_chunk)
                    rstart, rlen = next(rpr, (None, None))
        while 1:
            if progress:
                progress(filenum, len(b))
            b = f.read(BLOB_READ_SIZE)
            ofs += len(b)
            if rpr:
                rstart, rlen = _uncache_ours_upto(fd, ofs, (rstart, rlen), rpr)
            if not b:
                break
            yield b
        if rpr:
            rstart, rlen = _uncache_ours_upto(fd, ofs, (rstart, rlen), rpr)


def _splitbuf(buf, basebits, fanbits):
    while 1:
        b = buf.peek(buf.used())
        (ofs, bits) = _helpers.splitbuf(b)
        if ofs:
            if ofs > BLOB_MAX:
                ofs = BLOB_MAX
                level = 0
            else:
                level = (bits-basebits)//fanbits  # integer division
            buf.eat(ofs)
            yield buffer(b, 0, ofs), level
        else:
            break
    while buf.used() >= BLOB_MAX:
        # limit max blob size
        yield buf.get(BLOB_MAX), 0


def _hashsplit_iter(files, progress):
    assert(BLOB_READ_SIZE > BLOB_MAX)
    basebits = _helpers.blobbits()
    fanbits = int(math.log(fanout or 128, 2))
    buf = Buf()
    for inblock in readfile_iter(files, progress):
        buf.put(inblock)
        for buf_and_level in _splitbuf(buf, basebits, fanbits):
            yield buf_and_level
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
        for buf_and_level in _hashsplit_iter([f], progress=prog):
            yield buf_and_level


def hashsplit_iter(files, keep_boundaries, progress):
    if keep_boundaries:
        return _hashsplit_iter_keep_boundaries(files, progress)
    else:
        return _hashsplit_iter(files, progress)


total_split = 0
def split_to_blobs(makeblob, files, keep_boundaries, progress):
    global total_split
    for (blob, level) in hashsplit_iter(files, keep_boundaries, progress):
        sha = makeblob(blob)
        total_split += len(blob)
        if progress_callback:
            progress_callback(len(blob))
        yield (sha, len(blob), level)


def _make_shalist(l):
    ofs = 0
    l = list(l)
    total = sum(size for mode,sha,size, in l)
    vlen = len(b'%x' % total)
    shalist = []
    for (mode, sha, size) in l:
        shalist.append((mode, b'%0*x' % (vlen,ofs), sha))
        ofs += size
    assert(ofs == total)
    return (shalist, total)


def _squish(maketree, stacks, n):
    i = 0
    while i < n or len(stacks[i]) >= MAX_PER_TREE:
        while len(stacks) <= i+1:
            stacks.append([])
        if len(stacks[i]) == 1:
            stacks[i+1] += stacks[i]
        elif stacks[i]:
            (shalist, size) = _make_shalist(stacks[i])
            tree = maketree(shalist)
            stacks[i+1].append((GIT_MODE_TREE, tree, size))
        stacks[i] = []
        i += 1


def split_to_shalist(makeblob, maketree, files,
                     keep_boundaries, progress=None):
    sl = split_to_blobs(makeblob, files, keep_boundaries, progress)
    assert(fanout != 0)
    if not fanout:
        shal = []
        for (sha,size,level) in sl:
            shal.append((GIT_MODE_FILE, sha, size))
        return _make_shalist(shal)[0]
    else:
        stacks = [[]]
        for (sha,size,level) in sl:
            stacks[0].append((GIT_MODE_FILE, sha, size))
            _squish(maketree, stacks, level)
        #log('stacks: %r\n' % [len(i) for i in stacks])
        _squish(maketree, stacks, len(stacks)-1)
        #log('stacks: %r\n' % [len(i) for i in stacks])
        return _make_shalist(stacks[-1])[0]


def split_to_blob_or_tree(makeblob, maketree, files,
                          keep_boundaries, progress=None):
    shalist = list(split_to_shalist(makeblob, maketree,
                                    files, keep_boundaries, progress))
    if len(shalist) == 1:
        return (shalist[0][0], shalist[0][2])
    elif len(shalist) == 0:
        return (GIT_MODE_FILE, makeblob(b''))
    else:
        return (GIT_MODE_TREE, maketree(shalist))


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
