import sys
import git, _hashsplit
from helpers import *

BLOB_LWM = 8192*2
BLOB_MAX = BLOB_LWM*2
BLOB_HWM = 1024*1024
progress_callback = None
max_pack_size = 1000*1000*1000  # larger packs will slow down pruning
max_pack_objects = 200*1000  # cache memory usage is about 83 bytes per object
fanout = 4096

class Buf:
    def __init__(self):
        self.data = ''
        self.start = 0

    def put(self, s):
        #log('oldsize=%d+%d adding=%d\n' % (len(self.data), self.start, len(s)))
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
    ofs = _hashsplit.splitbuf(b)
    if ofs:
        buf.eat(ofs)
        return buffer(b, 0, ofs)
    return None


def blobiter(files):
    for f in files:
        while 1:
            b = f.read(BLOB_HWM)
            if not b:
                break
            yield b


def hashsplit_iter(files):
    assert(BLOB_HWM > BLOB_MAX)
    buf = Buf()
    fi = blobiter(files)
    while 1:
        blob = splitbuf(buf)
        if blob:
            yield blob
        else:
            if buf.used() >= BLOB_MAX:
                # limit max blob size
                yield (buf.get(buf.used()), 0)
            while buf.used() < BLOB_HWM:
                bnew = next(fi)
                if not bnew:
                    # eof
                    if buf.used():
                        yield buf.get(buf.used())
                    return
                buf.put(bnew)


total_split = 0
def _split_to_shalist(w, files):
    global total_split
    ofs = 0
    for blob in hashsplit_iter(files):
        sha = w.new_blob(blob)
        total_split += len(blob)
        if w.outbytes >= max_pack_size or w.count >= max_pack_objects:
            w.breakpoint()
        if progress_callback:
            progress_callback(len(blob))
        yield ('100644', '%016x' % ofs, sha)
        ofs += len(blob)


def split_to_shalist(w, files):
    sl = _split_to_shalist(w, files)
    if not fanout:
        shalist = list(sl)
    else:
        shalist = []
        tmplist = []
        for e in sl:
            tmplist.append(e)
            if len(tmplist) >= fanout and len(tmplist) >= 3:
                shalist.append(('40000', tmplist[0][1], w.new_tree(tmplist)))
                tmplist = []
        shalist += tmplist
    return shalist


def split_to_blob_or_tree(w, files):
    shalist = list(split_to_shalist(w, files))
    if len(shalist) == 1:
        return (shalist[0][0], shalist[0][2])
    elif len(shalist) == 0:
        return ('100644', w.new_blob(''))
    else:
        return ('40000', w.new_tree(shalist))
