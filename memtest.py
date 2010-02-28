#!/usr/bin/env python
import sys, re, struct, mmap
import git, options
from helpers import *


def s_from_bytes(bytes):
    clist = [chr(b) for b in bytes]
    return ''.join(clist)


def report(count):
    fields = ['VmSize', 'VmRSS', 'VmData', 'VmStk']
    d = {}
    for line in open('/proc/self/status').readlines():
        l = re.split(r':\s*', line.strip(), 1)
        d[l[0]] = l[1]
    if count >= 0:
        e1 = count
        fields = [d[k] for k in fields]
    else:
        e1 = ''
    print ('%9s  ' + ('%10s ' * len(fields))) % tuple([e1] + fields)


optspec = """
memtest [-n elements] [-c cycles]
--
n,number=  number of objects per cycle
c,cycles=  number of cycles to run
ignore-midx  ignore .midx files, use only .idx files
"""
o = options.Options(sys.argv[0], optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal('no arguments expected')

git.ignore_midx = opt.ignore_midx

git.check_repo_or_die()
m = git.MultiPackIndex(git.repo('objects/pack'))

cycles = opt.cycles or 100
number = opt.number or 10000

report(-1)
f = open('/dev/urandom')
a = mmap.mmap(-1, 20)
report(0)
for c in xrange(cycles):
    for n in xrange(number):
        b = f.read(3)
        if 0:
            bytes = list(struct.unpack('!BBB', b)) + [0]*17
            bytes[2] &= 0xf0
            bin = struct.pack('!20s', s_from_bytes(bytes))
        else:
            a[0:2] = b[0:2]
            a[2] = chr(ord(b[2]) & 0xf0)
            bin = str(a[0:20])
        #print bin.encode('hex')
        m.exists(bin)
    report((c+1)*number)
