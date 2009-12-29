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


def do_main():
    buf = [0] * WINDOWSIZE
    sum = 0
    i = 0
    count = 0
    last_count = 0
    pipe = None

    while 1:
        c = sys.stdin.read(1)
        if not len(c): break
        c = ord(c)
        sum = stupidsum_add(sum, buf[i], c)
        buf[i] = c
        i = (i + 1) % WINDOWSIZE
        count += 1

        if (sum & (BLOBSIZE-1)) == ((~0) & (BLOBSIZE-1)):
            sys.stderr.write('SPLIT @ %-8d size=%-8d (%d/%d)\n'
                             % (count, count - last_count,
                                BLOBSIZE, WINDOWSIZE))
            last_count = count
            i = 0
            buf = [0] * WINDOWSIZE
            sum = 0
            if pipe:
                pipe.stdin.close()
                pipe.wait()
                pipe = None

        if not pipe:
            pipe = subprocess.Popen(['git', 'hash-object', '--stdin', '-w'],
                                    stdin=subprocess.PIPE)
        pipe.stdin.write(chr(c))


assert(WINDOWSIZE >= 32)
assert(BLOBSIZE >= 32)
test_sums()
do_main()
