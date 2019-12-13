
import os, struct, subprocess
from binascii import hexlify, unhexlify

from bup import git, vfs, vint
from bup.io import path_msg
from bup.helpers import (debug1, debug2, linereader, lines_until_sentinel, log, pending_raise)
from bup.repo import LocalRepo
from bup.vint import write_vuint

class BaseServer:
    def __init__(self, conn):
        self.conn = conn
        # This is temporary due to the subclassing. The subclassing will
        # go away in the future, and we'll make this a decorator instead.
        self._commands = [
            b'quit',
            b'help',
            b'init-dir',
            b'set-dir',
            b'list-indexes',
            b'send-index',
            b'receive-objects-v2',
            b'read-ref',
            b'update-ref',
            b'join',
            b'cat',
            b'cat-batch',
            b'refs',
            b'rev-list',
            b'resolve',
            b'config-get',
        ]

    def quit(self, args):
        # implementation is actually not here
        pass

    def help(self, args):
        self.conn.write(b'Commands:\n    %s\n' % b'\n    '.join(sorted(self._commands)))
        self.conn.ok()

    def _init_session(self, reinit_with_new_repopath=None):
        raise NotImplementedError("Subclasses must implement _init_session")

    def _init_dir(self, arg):
        raise NotImplementedError("Subclasses must implement _init_dir")

    def init_dir(self, arg):
        self._init_dir(arg)
        self._init_session(arg)
        self.conn.ok()

    def set_dir(self, arg):
        self._init_session(arg)
        self.conn.ok()

    def list_indexes(self, args):
        pass

    def send_index(self, args):
        pass

    def receive_objects_v2(self, args):
        pass

    def _read_ref(self, refname):
        raise NotImplementedError("Subclasses must implement _read_ref")

    def read_ref(self, refname):
        self._init_session()
        r = self._read_ref(refname)
        self.conn.write(b'%s\n' % hexlify(r) if r else b'')
        self.conn.ok()

    def update_ref(self, args):
        pass

    def join(self, args):
        pass

    # apocryphal alias
    def cat(self, args):
        return self.join(args)

    def cat_batch(self, args):
        pass

    def refs(self, args):
        pass

    def rev_list(self, args):
        pass

    def resolve(self, args):
        pass

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
            rest = len(words) > 1 and words[1] or b''
            if cmd == b'quit':
                break

            cmdattr = cmd.replace(b'-', b'_').decode('ascii', errors='replace')
            fn = getattr(self, cmdattr, None)
            if not cmd in commands or not callable(fn):
                raise Exception('unknown server command: %r\n' % line)
            fn(rest)

        debug1('bup server: done\n')


class BupServer(BaseServer):
    def __init__(self, conn):
        BaseServer.__init__(self, conn)
        self.suspended_w = None
        self.repo = None
        self.dumb_server_mode = False

    def _set_mode(self):
        self.dumb_server_mode = os.path.exists(git.repo(b'bup-dumb-server'))
        debug1('bup server: serving in %s mode\n'
               % (self.dumb_server_mode and 'dumb' or 'smart'))

    def _init_session(self, reinit_with_new_repopath=None):
        if reinit_with_new_repopath is None and git.repodir:
            if not self.repo:
                self.repo = LocalRepo()
            return
        git.check_repo_or_die(reinit_with_new_repopath)
        if self.repo:
            self.repo.close()
        self.repo = LocalRepo()
        debug1('bup server: bupdir is %s\n' % path_msg(git.repodir))
        self._set_mode()

    def _init_dir(self, arg):
        git.init_repo(arg)
        debug1('bup server: bupdir initialized: %s\n' % path_msg(git.repodir))

    def list_indexes(self, junk):
        self._init_session()
        suffix = b''
        if self.dumb_server_mode:
            suffix = b' load'
        for f in os.listdir(git.repo(b'objects/pack')):
            if f.endswith(b'.idx'):
                self.conn.write(b'%s%s\n' % (f, suffix))
        self.conn.ok()

    def send_index(self, name):
        self._init_session()
        assert(name.find(b'/') < 0)
        assert(name.endswith(b'.idx'))
        with git.open_idx(git.repo(b'objects/pack/%s' % name)) as idx:
            self.conn.write(struct.pack('!I', len(idx.map)))
            self.conn.write(idx.map)
        self.conn.ok()

    def receive_objects_v2(self, junk):
        self._init_session()
        if self.suspended_w:
            w = self.suspended_w
            self.suspended_w = None
        else:
            if self.dumb_server_mode:
                w = git.PackWriter(objcache_maker=None, run_midx=False)
            else:
                w = git.PackWriter()
        try:
            suggested = set()
            while 1:
                ns = self.conn.read(4)
                if not ns:
                    w.abort()
                    raise Exception('object read: expected length header, got EOF\n')
                n = struct.unpack('!I', ns)[0]
                #debug2('expecting %d bytes\n' % n)
                if not n:
                    debug1('bup server: received %d object%s.\n'
                        % (w.count, w.count!=1 and "s" or ''))
                    fullpath = w.close()
                    w = None
                    if fullpath:
                        dir, name = os.path.split(fullpath)
                        self.conn.write(b'%s.idx\n' % name)
                    self.conn.ok()
                    return
                elif n == 0xffffffff:
                    debug2('bup server: receive-objects suspending.\n')
                    self.suspended_w = w
                    w = None
                    self.conn.ok()
                    return

                shar = self.conn.read(20)
                crcr = struct.unpack('!I', self.conn.read(4))[0]
                n -= 20 + 4
                buf = self.conn.read(n)  # object sizes in bup are reasonably small
                #debug2('read %d bytes\n' % n)
                self._check(w, n, len(buf), 'object read: expected %d bytes, got %d\n')
                if not self.dumb_server_mode:
                    oldpack = w.exists(shar, want_source=True)
                    if oldpack:
                        assert(not oldpack == True)
                        assert(oldpack.endswith(b'.idx'))
                        (dir,name) = os.path.split(oldpack)
                        if not (name in suggested):
                            debug1("bup server: suggesting index %s\n"
                                   % git.shorten_hash(name).decode('ascii'))
                            debug1("bup server:   because of object %s\n"
                                   % hexlify(shar))
                            self.conn.write(b'index %s\n' % name)
                            suggested.add(name)
                        continue
                nw, crc = w._raw_write((buf,), sha=shar)
                self._check(w, crcr, crc, 'object read: expected crc %d, got %d\n')
        # py2: this clause is unneeded with py3
        except BaseException as ex:
            with pending_raise(ex):
                if w:
                    w, w_tmp = None, w
                    w_tmp.close()
        finally:
            if w: w.close()
        assert False  # should be unreachable

    def _check(self, w, expected, actual, msg):
        if expected != actual:
            w.abort()
            raise Exception(msg % (expected, actual))

    def _read_ref(self, refname):
        return git.read_ref(refname)

    def update_ref(self, refname):
        self._init_session()
        newval = self.conn.readline().strip()
        oldval = self.conn.readline().strip()
        git.update_ref(refname, unhexlify(newval), unhexlify(oldval))
        self.conn.ok()

    def join(self, id):
        self._init_session()
        try:
            for blob in git.cp().join(id):
                self.conn.write(struct.pack('!I', len(blob)))
                self.conn.write(blob)
        except KeyError as e:
            log('server: error: %s\n' % e)
            self.conn.write(b'\0\0\0\0')
            self.conn.error(str(e).encode('utf-8'))
        else:
            self.conn.write(b'\0\0\0\0')
            self.conn.ok()

    def cat_batch(self, dummy):
        self._init_session()
        cat_pipe = git.cp()
        # For now, avoid potential deadlock by just reading them all
        for ref in tuple(lines_until_sentinel(self.conn, b'\n', Exception)):
            ref = ref[:-1]
            it = cat_pipe.get(ref)
            info = next(it)
            if not info[0]:
                self.conn.write(b'missing\n')
                continue
            self.conn.write(b'%s %s %d\n' % info)
            for buf in it:
                self.conn.write(buf)
        self.conn.ok()

    def refs(self, args):
        limit_to_heads, limit_to_tags = args.split()
        assert limit_to_heads in (b'0', b'1')
        assert limit_to_tags in (b'0', b'1')
        limit_to_heads = int(limit_to_heads)
        limit_to_tags = int(limit_to_tags)
        self._init_session()
        patterns = tuple(x[:-1] for x in lines_until_sentinel(self.conn, b'\n', Exception))
        for name, oid in git.list_refs(patterns=patterns,
                                       limit_to_heads=limit_to_heads,
                                       limit_to_tags=limit_to_tags):
            assert b'\n' not in name
            self.conn.write(b'%s %s\n' % (hexlify(oid), name))
        self.conn.write(b'\n')
        self.conn.ok()

    def rev_list(self, _):
        self._init_session()
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
        args = git.rev_list_invocation(refs, format=fmt)
        p = subprocess.Popen(args, env=git._gitenv(git.repodir),
                             stdout=subprocess.PIPE)
        while True:
            out = p.stdout.read(64 * 1024)
            if not out:
                break
            self.conn.write(out)
        self.conn.write(b'\n')
        rv = p.wait()  # not fatal
        if rv:
            msg = b'git rev-list returned error %d' % rv
            self.conn.error(msg)
            raise git.GitError(msg)
        self.conn.ok()

    def resolve(self, args):
        self._init_session()
        (flags,) = args.split()
        flags = int(flags)
        want_meta = bool(flags & 1)
        follow = bool(flags & 2)
        have_parent = bool(flags & 4)
        parent = vfs.read_resolution(self.conn) if have_parent else None
        path = vint.read_bvec(self.conn)
        if not len(path):
            raise Exception('Empty resolve path')
        try:
            res = list(vfs.resolve(self.repo, path, parent=parent, want_meta=want_meta,
                                   follow=follow))
        except vfs.IOError as ex:
            res = ex
        if isinstance(res, vfs.IOError):
            self.conn.write(b'\0')  # error
            vfs.write_ioerror(self.conn, res)
        else:
            self.conn.write(b'\1')  # success
            vfs.write_resolution(self.conn, res)
        self.conn.ok()

    def config_get(self, args):
        self._init_session()
        assert not args
        key, opttype = vint.recv(self.conn, 'ss')
        if key in (b'bup.split-trees',):
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

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        with pending_raise(value, rethrow=False):
            if self.suspended_w:
                self.suspended_w.close()
            if self.repo:
                self.repo.close()
