#!/usr/bin/env python
import sys, os, subprocess, errno, zlib, time, getopt
import hashsplit
import git
from helpers import *

BLOB_LWM = 8192*2
BLOB_MAX = BLOB_LWM*2
BLOB_HWM = 1024*1024


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
    ofs = hashsplit.splitbuf(b)
    if ofs:
        buf.eat(ofs)
        return buffer(b, 0, ofs)
    return None


def hashsplit_iter(f):
    ofs = 0
    buf = Buf()
    blob = 1

    eof = 0
    lv = 0
    while blob or not eof:
        if not eof and (buf.used() < BLOB_LWM or not blob):
            bnew = sys.stdin.read(BLOB_HWM)
            if not len(bnew): eof = 1
            #log('got %d, total %d\n' % (len(bnew), buf.used()))
            buf.put(bnew)

        blob = splitbuf(buf)
        if eof and not blob:
            blob = buf.get(buf.used())
        if not blob and buf.used() >= BLOB_MAX:
            blob = buf.get(BLOB_MAX)  # limit max blob size
        if not blob and not eof:
            continue

        if blob:
            yield (ofs, len(blob), git.hash_blob(blob))
            ofs += len(blob)
          
        nv = (ofs + buf.used())/1000000
        if nv != lv:
            log('%d\t' % nv)
            lv = nv
            
            
def usage():
    log('Usage: bup split [-t] <filename\n')
    exit(97)
    
gen_tree = False

def argparse(usage, argv, shortopts, allow_extra):
    try:
        (flags,extra) = getopt.getopt(argv[1:], shortopts)
    except getopt.GetoptError, e:
        log('%s: %s\n' % (argv[0], e))
        usage()
    if extra and not allow_extra:
        log('%s: invalid argument "%s"\n' % (argv[0], extra[0]))
        usage()
    return flags


flags = argparse(usage, sys.argv, 't', False)
for (flag,parm) in flags:
    if flag == '-t':
        gen_tree = True


start_time = time.time()
shalist = []

for (ofs, size, sha) in hashsplit_iter(sys.stdin):
    #log('SPLIT @ %-8d size=%-8d\n' % (ofs, size))
    if not gen_tree:
        print sha
    shalist.append(('100644', '%016x.bupchunk' % ofs, sha))
if gen_tree:
    print git.gen_tree(shalist)

secs = time.time() - start_time
log('\n%.2fkbytes in %.2f secs = %.2f kbytes/sec\n'
    % (ofs/1024., secs, ofs/1024./secs))
