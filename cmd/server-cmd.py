#!/usr/bin/env python
import sys, struct, mmap
from bup import options, git
from bup.helpers import *

suspended_w = None


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
    idx = git.PackIdx(git.repo('objects/pack/%s' % name))
    conn.write(struct.pack('!I', len(idx.map)))
    conn.write(idx.map)
    conn.ok()


def receive_objects(conn, junk):
    global suspended_w
    git.check_repo_or_die()
    suggested = {}
    if suspended_w:
        w = suspended_w
        suspended_w = None
    else:
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
            fullpath = w.close()
            if fullpath:
                (dir, name) = os.path.split(fullpath)
                conn.write('%s.idx\n' % name)
            conn.ok()
            return
        elif n == 0xffffffff:
            log('bup server: receive-objects suspended.\n')
            suspended_w = w
            conn.ok()
            return
            
        buf = conn.read(n)  # object sizes in bup are reasonably small
        #log('read %d bytes\n' % n)
        if len(buf) < n:
            w.abort()
            raise Exception('object read: expected %d bytes, got %d\n'
                            % (n, len(buf)))
        (type, content) = git._decode_packobj(buf)
        sha = git.calc_hash(type, content)
        oldpack = w.exists(sha)
        # FIXME: we only suggest a single index per cycle, because the client
        # is currently dumb to download more than one per cycle anyway.
        # Actually we should fix the client, but this is a minor optimization
        # on the server side.
        if not suggested and \
          oldpack and (oldpack == True or oldpack.endswith('.midx')):
            # FIXME: we shouldn't really have to know about midx files
            # at this layer.  But exists() on a midx doesn't return the
            # packname (since it doesn't know)... probably we should just
            # fix that deficiency of midx files eventually, although it'll
            # make the files bigger.  This method is certainly not very
            # efficient.
            w.objcache.refresh(skip_midx = True)
            oldpack = w.objcache.exists(sha)
            log('new suggestion: %r\n' % oldpack)
            assert(oldpack)
            assert(oldpack != True)
            assert(not oldpack.endswith('.midx'))
            w.objcache.refresh(skip_midx = False)
        if not suggested and oldpack:
            assert(oldpack.endswith('.idx'))
            (dir,name) = os.path.split(oldpack)
            if not (name in suggested):
                log("bup server: suggesting index %s\n" % name)
                conn.write('index %s\n' % name)
                suggested[name] = 1
        else:
            w._raw_write([buf])
    # NOTREACHED


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


def cat(conn, id):
    git.check_repo_or_die()
    try:
        for blob in git.cat(id):
            conn.write(struct.pack('!I', len(blob)))
            conn.write(blob)
    except KeyError, e:
        log('server: error: %s\n' % e)
        conn.write('\0\0\0\0')
        conn.error(e)
    else:
        conn.write('\0\0\0\0')
        conn.ok()


optspec = """
bup server
"""
o = options.Options('bup server', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal('no arguments expected')

log('bup server: reading from stdin.\n')

commands = {
    'init-dir': init_dir,
    'set-dir': set_dir,
    'list-indexes': list_indexes,
    'send-index': send_index,
    'receive-objects': receive_objects,
    'read-ref': read_ref,
    'update-ref': update_ref,
    'cat': cat,
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
