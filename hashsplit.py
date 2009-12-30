#!/usr/bin/env python
import sys, os, subprocess, errno, zlib, time
import hashsplit
from sha import sha

# FIXME: duplicated in C module.  This shouldn't really be here at all...
BLOBBITS = 14
BLOBSIZE = 1 << (BLOBBITS-1)


def log(s):
    sys.stderr.write('%s\n' % s)


class Buf:
    def __init__(self):
        self.list = []
        self.total = 0

    def put(self, s):
        if s:
            self.list.append(s)
            self.total += len(s)

    def get(self, count):
        count = count
        out = []
        while count > 0 and self.list:
            n = len(self.list[0])
            if count >= n:
                out.append(self.list[0])
                self.list = self.list[1:]
            else:
                n = count
                out.append(self.list[0][:n])
                self.list[0] = self.list[0][n:]
            count -= n
            self.total -= n
        return ''.join(out)

    def used(self):
        return self.total


def splitbuf(buf):
    #return buf.get(BLOBSIZE)
    b = buf.get(buf.used())
    try:
        ofs = hashsplit.splitbuf(b)
        if ofs:
            return b[:ofs]
    finally:
        buf.put(b[ofs:])
    return None


def save_blob(blob):
    header = 'blob %d\0' % len(blob)
    sum = sha(header)
    sum.update(blob)
    hex = sum.hexdigest()
    dir = '.git/objects/%s' % hex[0:2]
    fn = '%s/%s' % (dir, hex[2:])
    try:
        os.makedirs(dir)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise
    if not os.path.exists(fn):
        #log('creating %s' % fn)
        tfn = '%s.%d' % (fn, os.getpid())
        f = open(tfn, 'w')
        z = zlib.compressobj(1)
        f.write(z.compress(header))
        f.write(z.compress(blob))
        f.write(z.flush())
        f.close()
        os.rename(tfn, fn)
    else:
        #log('exists %s' % fn)
        pass
    print hex
    return hex


def do_main():
    start_time = time.time()
    ofs = 0
    buf = Buf()
    blob = 1

    eof = 0
    lv = 0
    while blob or not eof:
        if not eof and (buf.used() < BLOBSIZE*2 or not blob):
            bnew = sys.stdin.read(BLOBSIZE*4)
            if not len(bnew): eof = 1
            #log('got %d, total %d' % (len(bnew), buf.used()))
            buf.put(bnew)

        blob = splitbuf(buf)
        if eof and not blob:
            blob = buf.get(buf.used())
        if not blob and buf.used() >= BLOBSIZE*8:
            blob = buf.get(BLOBSIZE*4)  # limit max blob size
        if not blob and not eof:
            continue

        if blob:
            ofs += len(blob)
            #log('SPLIT @ %-8d size=%-8d (blobsize=%d)'
            #    % (ofs, len(blob), BLOBSIZE))
            save_blob(blob)
          
        nv = (ofs + buf.used())/1000000
        if nv != lv:
            log(nv)
            lv = nv
    secs = time.time() - start_time
    log('\n%.2fkbytes in %.2f secs = %.2f kbytes/sec' 
        % (ofs/1024., secs, ofs/1024./secs))


assert(BLOBSIZE >= 32)
do_main()
