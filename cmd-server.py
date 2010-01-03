#!/usr/bin/env python
import sys, struct, mmap
import options, git
from helpers import *


def list_indexes(conn):
    for f in os.listdir(git.repo('objects/pack')):
        if f.endswith('.idx'):
            conn.write('%s\n' % f)
    conn.ok()


def send_index(conn, name):
    assert(name.find('/') < 0)
    assert(name.endswith('.idx'))
    idx = git.PackIndex(git.repo('objects/pack/%s' % name))
    conn.write(struct.pack('!I', len(idx.map)))
    conn.write(idx.map)
    conn.ok()
    
            
def receive_objects(conn):
    w = git.PackWriter()
    while 1:
        ns = conn.read(4)
        if not ns:
            w.abort()
            raise Exception('object read: expected length header, got EOF\n')
        n = struct.unpack('!I', ns)[0]
        #log('expecting %d bytes\n' % n)
        if not n:
            log('bup server: received %d object%s.\n' 
                % (w.count, w.count!=1 and "s" or ''))
            w.close()
            return
        buf = conn.read(n)  # object sizes in bup are reasonably small
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

# FIXME: this protocol is totally lame and not at all future-proof
conn = Conn(sys.stdin, sys.stdout)
lr = linereader(conn)
for _line in lr:
    line = _line.strip()
    if not line:
        continue
    log('bup server: command: %r\n' % line)
    if line == 'quit':
        break
    elif line.startswith('set-dir '):
        git.repodir = line[8:]
        git.check_repo_or_die()
        log('bup server: bupdir is %r\n' % git.repodir)
        conn.ok()
    elif line == 'list-indexes':
        list_indexes(conn)
    elif line.startswith('send-index '):
        send_index(conn, line[11:])
    elif line == 'receive-objects':
        git.check_repo_or_die()
        receive_objects(conn)
        conn.ok()
    else:
        raise Exception('unknown server command: %r\n' % line)

log('bup server: done\n')
