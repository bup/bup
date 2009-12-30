#!/usr/bin/env python
import sys, subprocess

BLOBBITS = 14
BLOBSIZE = 1 << (BLOBBITS-1)
WINDOWBITS = 7
WINDOWSIZE = 1 << (WINDOWBITS-1)

# FIXME: replace this with a not-stupid rolling checksum algorithm,
# such as the one used in rsync (Adler32?)
def stupidsum_add(old, drop, add):
    return (((old<<1) | ((old>>31)&0xffffffff)) & 0xffffffff) ^ drop ^ add


def test_sums():
    sum = 0
    for i in range(WINDOWSIZE):
        sum = stupidsum_add(sum, 0, i%256)
    sum1 = sum
    for i in range(WINDOWSIZE*5):
        sum = stupidsum_add(sum, i%256, i%256)
    assert(sum == sum1)
    for i in range(WINDOWSIZE):
        sum = stupidsum_add(sum, i%256, 0)
    assert(sum == 0)


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
    window = [0] * WINDOWSIZE
    sum = 0
    i = 0
    count = 0
    for ent in buf.list:
        for c in ent:
            count += 1
            b = ord(c)
            sum = stupidsum_add(sum, window[i], b)
            window[i] = b
            i = (i + 1) % WINDOWSIZE
            if (sum & (BLOBSIZE-1)) == ((~0) & (BLOBSIZE-1)):
                return buf.get(count)
    return None


def save_blob(blob):
    pipe = subprocess.Popen(['git', 'hash-object', '--stdin', '-w'],
                            stdin=subprocess.PIPE)
    pipe.stdin.write(blob)
    pipe.stdin.close()
    pipe.wait()
    pipe = None


def do_main():
    ofs = 0
    buf = Buf()
    blob = 1

    eof = 0
    while blob or not eof:
        if not eof and (buf.used() < BLOBSIZE*2 or not blob):
            bnew = sys.stdin.read(BLOBSIZE*4)
            if not len(bnew): eof = 1
            # print 'got %d, total %d' % (len(bnew), buf.used())
            buf.put(bnew)

        blob = splitbuf(buf)
        if not blob and not eof:
            continue
        if eof and not blob:
            blob = buf.get(buf.used())

        if blob:
            ofs += len(blob)
            sys.stderr.write('SPLIT @ %-8d size=%-8d (%d/%d)\n'
                             % (ofs, len(blob), BLOBSIZE, WINDOWSIZE))
            save_blob(blob)

assert(WINDOWSIZE >= 32)
assert(BLOBSIZE >= 32)
test_sums()
do_main()
