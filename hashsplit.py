import sys
import git, _hashsplit
from helpers import *

BLOB_LWM = 8192*2
BLOB_MAX = BLOB_LWM*2
BLOB_HWM = 1024*1024
split_verbosely = 0
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
        if split_verbosely >= 2:
            log('.')
        buf.eat(ofs)
        return buffer(b, 0, ofs)
    return None


def blobiter(files):
    for f in files:
        b = 1
        while b:
            b = f.read(BLOB_HWM)
            if b:
                yield b
    yield '' # EOF indicator


def autofiles(filenames):
    if not filenames:
        yield sys.stdin
    else:
        for n in filenames:
            yield open(n)
            
    
def hashsplit_iter(w, files):
    ofs = 0
    buf = Buf()
    fi = blobiter(files)
    blob = 1

    eof = 0
    lv = 0
    while blob or not eof:
        if not eof and (buf.used() < BLOB_LWM or not blob):
            bnew = fi.next()
            if not bnew: eof = 1
            #log('got %d, total %d\n' % (len(bnew), buf.used()))
            buf.put(bnew)

        blob = splitbuf(buf)
        if eof and not blob:
            blob = buf.get(buf.used())
        if not blob and buf.used() >= BLOB_MAX:
            blob = buf.get(buf.used())  # limit max blob size
        if not blob and not eof:
            continue

        if blob:
            if w.outbytes >= max_pack_size or w.count >= max_pack_objects:
                w.breakpoint()
            yield (ofs, len(blob), w.new_blob(blob))
            ofs += len(blob)
          
        nv = (ofs + buf.used())/1000000
        if nv != lv:
            if split_verbosely >= 1:
                log('%d\t' % nv)
            lv = nv


total_split = 0
def _split_to_shalist(w, files):
    global total_split
    ofs = 0
    last_ofs = 0
    for (ofs, size, sha) in hashsplit_iter(w, files):
        #log('SPLIT @ %-8d size=%-8d\n' % (ofs, size))
        # this silliness keeps chunk filenames "similar" when a file changes
        # slightly.
        bm = BLOB_MAX
        while 1:
            cn = ofs / bm * bm
            #log('%x,%x,%x,%x\n' % (last_ofs,ofs,cn,bm))
            if cn > last_ofs or ofs == last_ofs: break
            bm /= 2
        last_ofs = cn
        total_split += size
        if progress_callback:
            progress_callback(size)
        yield ('100644', 'bup.chunk.%016x' % cn, sha)


def _next(i):
    try:
        return i.next()
    except StopIteration:
        return None


def split_to_shalist(w, files):
    sl = iter(_split_to_shalist(w, files))
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
