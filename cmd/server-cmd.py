#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import os, sys, struct, subprocess

from bup import options, git, vfs, vint
from bup.compat import hexstr
from bup.git import MissingObject
from bup.helpers import (Conn, debug1, debug2, linereader, lines_until_sentinel,
                         log)
from bup.repo import LocalRepo


suspended_w = None
dumb_server_mode = False
repo = None

def do_help(conn, junk):
    conn.write('Commands:\n    %s\n' % '\n    '.join(sorted(commands)))
    conn.ok()


def _set_mode():
    global dumb_server_mode
    dumb_server_mode = os.path.exists(git.repo('bup-dumb-server'))
    debug1('bup server: serving in %s mode\n' 
           % (dumb_server_mode and 'dumb' or 'smart'))


def _init_session(reinit_with_new_repopath=None):
    global repo
    if reinit_with_new_repopath is None and git.repodir:
        if not repo:
            repo = LocalRepo()
        return
    git.check_repo_or_die(reinit_with_new_repopath)
    if repo:
        repo.close()
    repo = LocalRepo()
    # OK. we now know the path is a proper repository. Record this path in the
    # environment so that subprocesses inherit it and know where to operate.
    os.environ['BUP_DIR'] = git.repodir
    debug1('bup server: bupdir is %r\n' % git.repodir)
    _set_mode()


def init_dir(conn, arg):
    git.init_repo(arg)
    debug1('bup server: bupdir initialized: %r\n' % git.repodir)
    _init_session(arg)
    conn.ok()


def set_dir(conn, arg):
    _init_session(arg)
    conn.ok()

    
def list_indexes(conn, junk):
    _init_session()
    suffix = ''
    if dumb_server_mode:
        suffix = ' load'
    for f in os.listdir(git.repo('objects/pack')):
        if f.endswith('.idx'):
            conn.write('%s%s\n' % (f, suffix))
    conn.ok()


def send_index(conn, name):
    _init_session()
    assert(name.find('/') < 0)
    assert(name.endswith('.idx'))
    idx = git.open_idx(git.repo('objects/pack/%s' % name))
    conn.write(struct.pack('!I', len(idx.map)))
    conn.write(idx.map)
    conn.ok()


def receive_objects_v2(conn, junk):
    global suspended_w
    _init_session()
    suggested = set()
    if suspended_w:
        w = suspended_w
        suspended_w = None
    else:
        if dumb_server_mode:
            w = git.PackWriter(objcache_maker=None)
        else:
            w = git.PackWriter()
    while 1:
        ns = conn.read(4)
        if not ns:
            w.abort()
            raise Exception('object read: expected length header, got EOF\n')
        n = struct.unpack('!I', ns)[0]
        #debug2('expecting %d bytes\n' % n)
        if not n:
            debug1('bup server: received %d object%s.\n' 
                % (w.count, w.count!=1 and "s" or ''))
            fullpath = w.close(run_midx=not dumb_server_mode)
            if fullpath:
                (dir, name) = os.path.split(fullpath)
                conn.write('%s.idx\n' % name)
            conn.ok()
            return
        elif n == 0xffffffff:
            debug2('bup server: receive-objects suspended.\n')
            suspended_w = w
            conn.ok()
            return
            
        shar = conn.read(20)
        crcr = struct.unpack('!I', conn.read(4))[0]
        n -= 20 + 4
        buf = conn.read(n)  # object sizes in bup are reasonably small
        #debug2('read %d bytes\n' % n)
        _check(w, n, len(buf), 'object read: expected %d bytes, got %d\n')
        if not dumb_server_mode:
            oldpack = w.exists(shar, want_source=True)
            if oldpack:
                assert(not oldpack == True)
                assert(oldpack.endswith('.idx'))
                (dir,name) = os.path.split(oldpack)
                if not (name in suggested):
                    debug1("bup server: suggesting index %s\n"
                           % git.shorten_hash(name))
                    debug1("bup server:   because of object %s\n"
                           % hexstr(shar))
                    conn.write('index %s\n' % name)
                    suggested.add(name)
                continue
        nw, crc = w._raw_write((buf,), sha=shar)
        _check(w, crcr, crc, 'object read: expected crc %d, got %d\n')
    # NOTREACHED
    

def _check(w, expected, actual, msg):
    if expected != actual:
        w.abort()
        raise Exception(msg % (expected, actual))


def read_ref(conn, refname):
    _init_session()
    r = git.read_ref(refname)
    conn.write('%s\n' % (r or '').encode('hex'))
    conn.ok()


def update_ref(conn, refname):
    _init_session()
    newval = conn.readline().strip()
    oldval = conn.readline().strip()
    git.update_ref(refname, newval.decode('hex'), oldval.decode('hex'))
    conn.ok()

def join(conn, id):
    _init_session()
    try:
        for blob in git.cp().join(id):
            conn.write(struct.pack('!I', len(blob)))
            conn.write(blob)
    except KeyError as e:
        log('server: error: %s\n' % e)
        conn.write('\0\0\0\0')
        conn.error(e)
    else:
        conn.write('\0\0\0\0')
        conn.ok()

def cat_batch(conn, dummy):
    _init_session()
    cat_pipe = git.cp()
    # For now, avoid potential deadlock by just reading them all
    for ref in tuple(lines_until_sentinel(conn, '\n', Exception)):
        ref = ref[:-1]
        it = cat_pipe.get(ref)
        info = next(it)
        if not info[0]:
            conn.write('missing\n')
            continue
        conn.write('%s %s %d\n' % info)
        for buf in it:
            conn.write(buf)
    conn.ok()

def refs(conn, args):
    limit_to_heads, limit_to_tags = args.split()
    assert limit_to_heads in ('0', '1')
    assert limit_to_tags in ('0', '1')
    limit_to_heads = int(limit_to_heads)
    limit_to_tags = int(limit_to_tags)
    _init_session()
    patterns = tuple(x[:-1] for x in lines_until_sentinel(conn, '\n', Exception))
    for name, oid in git.list_refs(patterns=patterns,
                                   limit_to_heads=limit_to_heads,
                                   limit_to_tags=limit_to_tags):
        assert '\n' not in name
        conn.write('%s %s\n' % (oid.encode('hex'), name))
    conn.write('\n')
    conn.ok()

def rev_list(conn, _):
    _init_session()
    count = conn.readline()
    if not count:
        raise Exception('Unexpected EOF while reading rev-list count')
    count = None if count == '\n' else int(count)
    fmt = conn.readline()
    if not fmt:
        raise Exception('Unexpected EOF while reading rev-list format')
    fmt = None if fmt == '\n' else fmt[:-1]
    refs = tuple(x[:-1] for x in lines_until_sentinel(conn, '\n', Exception))
    args = git.rev_list_invocation(refs, count=count, format=fmt)
    p = subprocess.Popen(git.rev_list_invocation(refs, count=count, format=fmt),
                         env=git._gitenv(git.repodir),
                         stdout=subprocess.PIPE)
    while True:
        out = p.stdout.read(64 * 1024)
        if not out:
            break
        conn.write(out)
    conn.write('\n')
    rv = p.wait()  # not fatal
    if rv:
        msg = 'git rev-list returned error %d' % rv
        conn.error(msg)
        raise GitError(msg)
    conn.ok()

def resolve(conn, args):
    _init_session()
    (flags,) = args.split()
    flags = int(flags)
    want_meta = bool(flags & 1)
    follow = bool(flags & 2)
    have_parent = bool(flags & 4)
    parent = vfs.read_resolution(conn) if have_parent else None
    path = vint.read_bvec(conn)
    if not len(path):
        raise Exception('Empty resolve path')
    try:
        res = list(vfs.resolve(repo, path, parent=parent, want_meta=want_meta,
                               follow=follow))
    except vfs.IOError as ex:
        res = ex
    if isinstance(res, vfs.IOError):
        conn.write(b'\0')  # error
        vfs.write_ioerror(conn, res)
    else:
        conn.write(b'\1')  # success
        vfs.write_resolution(conn, res)
    conn.ok()

optspec = """
bup server
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal('no arguments expected')

debug2('bup server: reading from stdin.\n')

commands = {
    'quit': None,
    'help': do_help,
    'init-dir': init_dir,
    'set-dir': set_dir,
    'list-indexes': list_indexes,
    'send-index': send_index,
    'receive-objects-v2': receive_objects_v2,
    'read-ref': read_ref,
    'update-ref': update_ref,
    'join': join,
    'cat': join,  # apocryphal alias
    'cat-batch' : cat_batch,
    'refs': refs,
    'rev-list': rev_list,
    'resolve': resolve
}

# FIXME: this protocol is totally lame and not at all future-proof.
# (Especially since we abort completely as soon as *anything* bad happens)
conn = Conn(sys.stdin, sys.stdout)
lr = linereader(conn)
for _line in lr:
    line = _line.strip()
    if not line:
        continue
    debug1('bup server: command: %r\n' % line)
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

debug1('bup server: done\n')
