
import os, struct
from binascii import hexlify, unhexlify

from bup import git, vfs, vint
from bup.compat import hexstr
from bup.io import path_msg
from bup.vint import read_bvec, write_bvec
from bup.vint import read_vint, write_vint
from bup.vint import read_vuint, write_vuint
from bup.helpers import (debug1, debug2, linereader, lines_until_sentinel, log, pending_raise)
from bup.vint import write_vuint
from bup.vfs import Item, Chunky, RevList, Root, Tags, Commit, FakeLink
from bup.metadata import Metadata


def read_item(port):
    def read_m(port, has_meta):
        if has_meta:
            m = Metadata.read(port)
            return m
        return read_vuint(port)
    kind, has_meta = vint.recv(port, 'sV')
    if kind == b'Item':
        oid, meta = read_bvec(port), read_m(port, has_meta)
        return Item(oid=oid, meta=meta)
    if kind == b'Chunky':
        oid, meta = read_bvec(port), read_m(port, has_meta)
        return Chunky(oid=oid, meta=meta)
    if kind == b'RevList':
        oid, meta = read_bvec(port), read_m(port, has_meta)
        return RevList(oid=oid, meta=meta)
    if kind == b'Root':
        return Root(meta=read_m(port, has_meta))
    if kind == b'Tags':
        return Tags(meta=read_m(port, has_meta))
    if kind == b'Commit':
        oid, coid = vint.recv(port, 'ss')
        meta = read_m(port, has_meta)
        return Commit(oid=oid, coid=coid, meta=meta)
    if kind == b'FakeLink':
        target, meta = read_bvec(port), read_m(port, has_meta)
        return FakeLink(target=target, meta=meta)
    assert False

def write_item(port, item):
    kind = type(item)
    name = bytes(kind.__name__.encode('ascii'))
    meta = item.meta
    has_meta = 1 if isinstance(meta, Metadata) else 0
    if kind in (Item, Chunky, RevList):
        assert len(item.oid) == 20
        if has_meta:
            vint.send(port, 'sVs', name, has_meta, item.oid)
            Metadata.write(meta, port, include_path=False)
        else:
            vint.send(port, 'sVsV', name, has_meta, item.oid, item.meta)
    elif kind in (Root, Tags):
        if has_meta:
            vint.send(port, 'sV', name, has_meta)
            Metadata.write(meta, port, include_path=False)
        else:
            vint.send(port, 'sVV', name, has_meta, item.meta)
    elif kind == Commit:
        assert len(item.oid) == 20
        assert len(item.coid) == 20
        if has_meta:
            vint.send(port, 'sVss', name, has_meta, item.oid, item.coid)
            Metadata.write(meta, port, include_path=False)
        else:
            vint.send(port, 'sVssV', name, has_meta, item.oid, item.coid,
                      item.meta)
    elif kind == FakeLink:
        if has_meta:
            vint.send(port, 'sVs', name, has_meta, item.target)
            Metadata.write(meta, port, include_path=False)
        else:
            vint.send(port, 'sVsV', name, has_meta, item.target, item.meta)
    else:
        assert False

def write_ioerror(port, ex):
    assert isinstance(ex, vfs.IOError)
    write_vuint(port,
                (1 if ex.errno is not None else 0)
                | (2 if ex.strerror is not None else 0)
                | (4 if ex.terminus is not None else 0))
    if ex.errno is not None:
        write_vint(port, ex.errno)
    if ex.strerror is not None:
        write_bvec(port, ex.strerror.encode('utf-8'))
    if ex.terminus is not None:
        write_resolution(port, ex.terminus)

def read_ioerror(port):
    mask = read_vuint(port)
    no = read_vint(port) if 1 & mask else None
    msg = read_bvec(port).decode('utf-8') if 2 & mask else None
    term = read_resolution(port) if 4 & mask else None
    return vfs.IOError(errno=no, message=msg, terminus=term)

def write_resolution(port, resolution):
    write_vuint(port, len(resolution))
    for name, item in resolution:
        write_bvec(port, name)
        if item:
            port.write(b'\x01')
            write_item(port, item)
        else:
            port.write(b'\x00')

def read_resolution(port):
    n = read_vuint(port)
    result = []
    for i in range(n):
        name = read_bvec(port)
        have_item = ord(port.read(1))
        assert have_item in (0, 1)
        item = read_item(port) if have_item else None
        result.append((name, item))
    return tuple(result)

def _command(fn):
    fn.bup_server_command = True
    return fn

class Server:
    def __init__(self, conn, backend):
        self.conn = conn
        self._backend = backend
        self._commands = self._get_commands()
        self.suspended = False
        self.repo = None

    def _get_commands(self):
        commands = []
        for name in dir(self):
            fn = getattr(self, name)

            if getattr(fn, 'bup_server_command', False):
                commands.append(name.replace('_', '-').encode('ascii'))

        return commands

    @_command
    def quit(self, args):
        # implementation is actually not here
        pass

    @_command
    def help(self, args):
        self.conn.write(b'Commands:\n    %s\n' % b'\n    '.join(sorted(self._commands)))
        self.conn.ok()

    def init_session(self, repo_dir=None):
        if self.repo and repo_dir:
            self.repo.close()
            self.repo = None
            self.suspended = False
        if not self.repo:
            self.repo = self._backend(repo_dir, server=True)
            msgdir = path_msg(self.repo.repo_dir)
            if self.repo.dumb_server_mode:
                debug1('bup server: (%s mode) serving %s\n'
                       % (self.repo.dumb_server_mode and 'dumb' or 'smart',
                          path_msg(self.repo.repo_dir)))

    @_command
    def init_dir(self, arg):
        self._backend.create(arg)
        self.init_session(arg)
        self.conn.ok()

    @_command
    def set_dir(self, arg):
        self.init_session(arg)
        self.conn.ok()

    @_command
    def list_indexes(self, junk):
        self.init_session()
        suffix = b' load' if self.repo.dumb_server_mode else b''
        for f in self.repo.list_indexes():
            # must end with .idx to not confuse everything, so filter
            # here ... even if the subclass might not yield anything
            # else to start with
            if f.endswith(b'.idx'):
                self.conn.write(b'%s%s\n' % (f, suffix))
        self.conn.ok()

    def _send_size(self, size):
        self.conn.write(struct.pack('!I', size))

    @_command
    def send_index(self, name):
        self.init_session()
        assert(name.find(b'/') < 0)
        assert(name.endswith(b'.idx'))
        self.repo.send_index(name, self.conn, self._send_size)
        self.conn.ok()

    def _check(self, expected, actual, msg):
        if expected != actual:
            self.repo.abort_writing()
            raise Exception(msg % (expected, actual))

    @_command
    def receive_objects_v2(self, junk):
        self.init_session()
        if self.suspended:
            self.suspended = False
        # FIXME: this goes together with the direct accesses below
        self.repo._ensure_packwriter()
        suggested = set()
        while 1:
            ns = self.conn.read(4)
            if not ns:
                self.repo.abort_writing()
                raise Exception('object read: expected length header, got EOF\n')
            n = struct.unpack('!I', ns)[0]
            #debug2('expecting %d bytes\n' % n)
            if not n:
                # FIXME: don't be lazy and count ourselves, or something, at least
                # don't access self.repo internals
                debug1('bup server: received %d object%s.\n'
                    % (self.repo._packwriter.count,
                       self.repo._packwriter.count != 1 and "s" or ''))
                fullpath = self.repo.finish_writing()
                if fullpath:
                    dir, name = os.path.split(fullpath)
                    self.conn.write(b'%s.idx\n' % name)
                self.conn.ok()
                return
            elif n == 0xffffffff:
                debug2('bup server: receive-objects suspending.\n')
                self.suspended = True
                self.conn.ok()
                return

            shar = self.conn.read(20)
            crcr = struct.unpack('!I', self.conn.read(4))[0]
            n -= 20 + 4
            buf = self.conn.read(n)  # object sizes in bup are reasonably small
            #debug2('read %d bytes\n' % n)
            self._check(n, len(buf), 'object read: expected %d bytes, got %d\n')
            if not self.repo.dumb_server_mode:
                result = self.repo.exists(shar, want_source=True)
                if result:
                    oldpack = result.pack
                    assert(oldpack.endswith(b'.idx'))
                    (dir,name) = os.path.split(oldpack)
                    if not (name in suggested):
                        debug1("bup server: suggesting index %s\n"
                               % git.shorten_hash(name).decode('ascii'))
                        debug1("bup server:   because of object %s\n"
                               % hexstr(shar))
                        self.conn.write(b'index %s\n' % name)
                        suggested.add(name)
                    continue
            # FIXME: figure out the right abstraction for this; or better yet,
            #        make the protocol aware of the object type
            nw, crc = self.repo._packwriter._raw_write((buf,), sha=shar)
            self._check(crcr, crc, 'object read: expected crc %d, got %d\n')
        assert False  # should be unreachable

    @_command
    def read_ref(self, refname):
        self.init_session()
        r = self.repo.read_ref(refname)
        self.conn.write(b'%s\n' % hexlify(r or b''))
        self.conn.ok()

    @_command
    def update_ref(self, refname):
        self.init_session()
        newval = self.conn.readline().strip()
        oldval = self.conn.readline().strip()
        self.repo.update_ref(refname, unhexlify(newval), unhexlify(oldval))
        self.conn.ok()

    @_command
    def join(self, id):
        self.init_session()
        try:
            for blob in self.repo.join(id):
                self.conn.write(struct.pack('!I', len(blob)))
                self.conn.write(blob)
        except KeyError as e:
            msg = str(e)
            log(f'server: error: {msg}\n')
            self.conn.write(b'\0\0\0\0')
            self.conn.error(msg.encode('ascii', errors='backslashreplace'))
        else:
            self.conn.write(b'\0\0\0\0')
            self.conn.ok()

    cat = join # apocryphal alias

    @_command
    def cat_batch(self, dummy):
        self.init_session()
        # For now, avoid potential deadlock by just reading them all
        for ref in tuple(lines_until_sentinel(self.conn, b'\n', Exception)):
            ref = ref[:-1]
            it = self.repo.cat(ref)
            info = next(it)
            if not info[0]:
                self.conn.write(b'missing\n')
                continue
            self.conn.write(b'%s %s %d\n' % info)
            for buf in it:
                self.conn.write(buf)
        self.conn.ok()

    @_command
    def refs(self, args):
        limit_to_heads, limit_to_tags = args.split()
        assert limit_to_heads in (b'0', b'1')
        assert limit_to_tags in (b'0', b'1')
        limit_to_heads = int(limit_to_heads)
        limit_to_tags = int(limit_to_tags)
        self.init_session()
        patterns = tuple(x[:-1] for x in lines_until_sentinel(self.conn, b'\n', Exception))
        for name, oid in self.repo.refs(patterns, limit_to_heads, limit_to_tags):
            assert b'\n' not in name
            self.conn.write(b'%s %s\n' % (hexlify(oid), name))
        self.conn.write(b'\n')
        self.conn.ok()

    @_command
    def rev_list(self, _):
        self.init_session()
        count = self.conn.readline()
        if not count:
            raise Exception('Unexpected EOF while reading rev-list count')
        assert count == b'\n'
        count = None
        fmt = self.conn.readline()
        if not fmt:
            raise Exception('Unexpected EOF while reading rev-list format')
        fmt = None if fmt == b'\n' else fmt[:-1]
        refs = tuple(x[:-1] for x in lines_until_sentinel(self.conn, b'\n', Exception))

        try:
            for buf in self.repo.rev_list_raw(refs, fmt):
                self.conn.write(buf)
            self.conn.write(b'\n')
            self.conn.ok()
        except git.GitError as e:
            self.conn.error(str(e).encode('ascii', errors='backslashreplace'))
            raise

    @_command
    def resolve(self, args):
        self.init_session()
        (flags,) = args.split()
        flags = int(flags)
        want_meta = bool(flags & 1)
        follow = bool(flags & 2)
        have_parent = bool(flags & 4)
        parent = read_resolution(self.conn) if have_parent else None
        path = read_bvec(self.conn)
        if not len(path):
            raise Exception('Empty resolve path')
        try:
            res = list(self.repo.resolve(path, parent, want_meta, follow))
        except vfs.IOError as ex:
            res = ex
        if isinstance(res, vfs.IOError):
            self.conn.write(b'\0')  # error
            write_ioerror(self.conn, res)
        else:
            self.conn.write(b'\1')  # success
            write_resolution(self.conn, res)
        self.conn.ok()

    @_command
    def config_get(self, args):
        self.init_session()
        assert not args
        key, opttype = vint.recv(self.conn, 'ss')
        if key in (b'bup.split.trees',
                   b'bup.split.files'):
            opttype = None if not len(opttype) else opttype.decode('ascii')
            val = self.repo.config_get(key, opttype=opttype)
            if val is None:
                write_vuint(self.conn, 0)
            elif isinstance(val, bool):
                write_vuint(self.conn, 1 if val else 2)
            elif isinstance(val, int):
                vint.send(self.conn, 'Vv', 3, val)
            elif isinstance(val, bytes):
                vint.send(self.conn, 'Vs', 4, val)
            else:
                raise TypeError(f'Unrecognized result type {type(val)}')
        else:
            write_vuint(self.conn, 5)
        self.conn.ok()

    def handle(self):
        commands = self._commands

        # FIXME: this protocol is totally lame and not at all future-proof.
        # (Especially since we abort completely as soon as *anything* bad happens)
        lr = linereader(self.conn)
        for _line in lr:
            line = _line.strip()
            if not line:
                continue
            debug1('bup server: command: %r\n' % line)
            words = line.split(b' ', 1)
            cmd = words[0]

            if not cmd in commands:
                raise Exception('unknown server command: %r\n' % line)

            rest = len(words) > 1 and words[1] or ''
            if cmd == b'quit':
                break

            cmdattr = cmd.replace(b'-', b'_').decode('ascii', errors='replace')
            getattr(self, cmdattr)(rest)

        debug1('bup server: done\n')

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        with pending_raise(value, rethrow=False): # Still needed with py3?
            try:
                if self.suspended:
                    self.repo.finish_writing()
            finally:
                if self.repo:
                    self.repo.close()
