#!/usr/bin/env python2.5
import sys, struct, mmap
import options, git
from helpers import *


def init_dir(conn, arg):
    git.init_repo(arg)
    log('bup server: bupdir initialized: %r\n' % git.repodir)
    conn.ok()


def set_dir(conn, arg):
    git.check_repo_or_die(arg)
    log('bup server: bupdir is %r\n' % git.repodir)
    conn.ok()

    
def list_indexes(conn, junk):
    git.check_repo_or_die()
    for f in os.listdir(git.repo('objects/pack')):
        if f.endswith('.idx'):
            conn.write('%s\n' % f)
    conn.ok()


def send_index(conn, name):
    git.check_repo_or_die()
    assert(name.find('/') < 0)
    assert(name.endswith('.idx'))
    idx = git.PackIndex(git.repo('objects/pack/%s' % name))
    conn.write(struct.pack('!I', len(idx.map)))
    conn.write(idx.map)
    conn.ok()
    
            
def receive_objects(conn, junk):
    git.check_repo_or_die()
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
    conn.ok()


def read_ref(conn, refname):
    git.check_repo_or_die()
    r = git.read_ref(refname)
    conn.write('%s\n' % (r or '').encode('hex'))
    conn.ok()


def update_ref(conn, refname):
    git.check_repo_or_die()
    newval = conn.readline().strip()
    oldval = conn.readline().strip()
    git.update_ref(refname, newval.decode('hex'), oldval.decode('hex'))
    conn.ok()


optspec = """
bup server
"""
o = options.Options('bup server', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    log('bup server: no arguments expected\n')
    o.usage()

log('bup server: reading from stdin.\n')

commands = {
    'init-dir': init_dir,
    'set-dir': set_dir,
    'list-indexes': list_indexes,
    'send-index': send_index,
    'receive-objects': receive_objects,
    'read-ref': read_ref,
    'update-ref': update_ref,
}

# FIXME: this protocol is totally lame and not at all future-proof.
# (Especially since we abort completely as soon as *anything* bad happens)
conn = Conn(sys.stdin, sys.stdout)
lr = linereader(conn)
for _line in lr:
    line = _line.strip()
    if not line:
        continue
    log('bup server: command: %r\n' % line)
    words = line.split(' ', 1)
    cmd = words[0]
    rest = len(words)>1 and words[1] or ''
    if cmd == 'quit':
        break
    else:
        cmd = commands.get(cmd)
        if cmd:
            cmd(conn, rest)
        else:
            raise Exception('unknown server command: %r\n' % line)

log('bup server: done\n')
