#!/usr/bin/env python
import sys, struct
import options, git
from helpers import *


def receive_objects(f):
    w = git.PackWriter()
    while 1:
        ns = f.read(4)
        if not ns:
            w.abort()
            raise Exception('object read: expected length header, got EOF\n')
        n = struct.unpack('!I', ns)[0]
        #log('expecting %d bytes\n' % n)
        if not n:
            w.close()
            return
        buf = f.read(n)
        #log('read %d bytes\n' % n)
        if len(buf) < n:
            w.abort()
            raise Exception('object read: expected %d bytes, got %d\n'
                            % (n, len(buf)))
        w._raw_write(buf)
    w.close()


optspec = """
bup server
"""
o = options.Options('bup server', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    log('bup server: no arguments expected\n')
    o.usage()

log('bup server: reading from stdin.\n')

f = sys.stdin
lr = linereader(f)
for _line in lr:
    line = _line.strip()
    if not line:
        continue
    log('bup server: command: %r\n' % line)
    if line == 'quit':
        break
    elif line == 'set-dir':
        git.repodir = lr.next()
        git.check_repo_or_die()
        log('bup server: bupdir is %r\n' % git.repodir)
    elif line == 'receive-objects':
        git.check_repo_or_die()
        receive_objects(f)
    else:
        raise Exception('unknown server command: %r\n' % line)

log('bup server: done\n')
