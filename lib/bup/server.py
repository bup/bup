from __future__ import absolute_import
import os, struct, subprocess
from binascii import hexlify, unhexlify

from bup import git, vfs, vint
from bup.compat import environ, hexstr, int_types
from bup.io import byte_stream, path_msg
from bup.git import MissingObject
from bup.helpers import (debug1, debug2, linereader, lines_until_sentinel, log)
from bup.repo import LocalRepo


class BaseServer:
    def __init__(self, conn):
        self.conn = conn
        self.dumb_server_mode = False
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

    def _list_indexes(self):
        """
        This should return a list of or be an iterator listing all
        the indexes present in the repository.
        """
        raise NotImplementedError('Subclasses must implement _list_indexes')

    def list_indexes(self, junk):
        self._init_session()
        suffix = b''
        if self.dumb_server_mode:
            suffix = b' load'
        for f in self._list_indexes():
            # must end with .idx to not confuse everything, so filter
            # here ... even if the subclass might not yield anything
            # else to start with
            if f.endswith(b'.idx'):
                self.conn.write(b'%s%s\n' % (f, suffix))
        self.conn.ok()

    def _send_index(self, name):
        """
        This should return a memory object whose len() can be determined
        and that can be written to the connection.
        """
        raise NotImplementedError("Subclasses must implement _send_index")

    def send_index(self, name):
        self._init_session()
        assert(name.find(b'/') < 0)
        assert(name.endswith(b'.idx'))
        data = self._send_index(name)
        self.conn.write(struct.pack('!I', len(data)))
        self.conn.write(data)
        self.conn.ok()

    def receive_objects_v2(self, args):
        pass

    def _read_ref(self, refname):
        raise NotImplementedError("Subclasses must implement _read_ref")

    def read_ref(self, refname):
        self._init_session()
        r = self._read_ref(refname)
        self.conn.write(b'%s\n' % hexlify(r) if r else b'')
        self.conn.ok()

    def _update_ref(self, refname, newval, oldval):
        """
        This updates the given ref from the old to the new value.
        """
        raise NotImplementedError("Subclasses must implemented _update_ref")

    def update_ref(self, refname):
        self._init_session()
        newval = self.conn.readline().strip()
        oldval = self.conn.readline().strip()
        self._update_ref(refname, unhexlify(newval), unhexlify(oldval))
        self.conn.ok()

    def _join(self, id):
        """
        This should yield all the blob data for the given id,
        may raise KeyError if not present.
        """
        raise NotImplemented("Subclasses must implemented _join")

    def join(self, id):
        self._init_session()
        try:
            for blob in self._join(id):
                self.conn.write(struct.pack('!I', len(blob)))
                self.conn.write(blob)
        except KeyError as e:
            log('server: error: %s\n' % str(e).encode('utf-8'))
            self.conn.write(b'\0\0\0\0')
            self.conn.error(e)
        else:
            self.conn.write(b'\0\0\0\0')
            self.conn.ok()

    cat = join # apocryphal alias

    def _cat(self, ref):
        """
        Retrieve one ref. This must return an iterator that yields
        (oidx, type, size), followed by the data referred to by ref,
        or only (None, None, None) if the ref doesn't exist.
        """
        raise NotImplementedError("Subclasses must implement _cat")

    def cat_batch(self, dummy):
        self._init_session()
        # For now, avoid potential deadlock by just reading them all
        for ref in tuple(lines_until_sentinel(self.conn, b'\n', Exception)):
            ref = ref[:-1]
            it = self._cat(ref)
            info = next(it)
            if not info[0]:
                self.conn.write(b'missing\n')
                continue
            self.conn.write(b'%s %s %d\n' % info)
            for buf in it:
                self.conn.write(buf)
        self.conn.ok()

    def _refs(self, patterns, limit_to_heads, limit_to_tags):
        """
        This should yield (name, oid) tuples according to the configuration
        passed in the arguments.
        """
        raise NotImplemented("Subclasses must implement _refs")

    def refs(self, args):
        limit_to_heads, limit_to_tags = args.split()
        assert limit_to_heads in (b'0', b'1')
        assert limit_to_tags in (b'0', b'1')
        limit_to_heads = int(limit_to_heads)
        limit_to_tags = int(limit_to_tags)
        self._init_session()
        patterns = tuple(x[:-1] for x in lines_until_sentinel(self.conn, b'\n', Exception))
        for name, oid in self._refs(patterns, limit_to_heads, limit_to_tags):
            assert b'\n' not in name
            self.conn.write(b'%s %s\n' % (hexlify(oid), name))
        self.conn.write(b'\n')
        self.conn.ok()

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

    def _list_indexes(self):
        for f in os.listdir(git.repo(b'objects/pack')):
            yield f

    def _send_index(self, name):
        return git.open_idx(git.repo(b'objects/pack/%s' % name)).map

    def receive_objects_v2(self, junk):
        self._init_session()
        suggested = set()
        if self.suspended_w:
            w = self.suspended_w
            self.suspended_w = None
        else:
            if self.dumb_server_mode:
                w = git.PackWriter(objcache_maker=None)
            else:
                w = git.PackWriter()
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
                fullpath = w.close(run_midx=not self.dumb_server_mode)
                if fullpath:
                    (dir, name) = os.path.split(fullpath)
                    self.conn.write(b'%s.idx\n' % name)
                self.conn.ok()
                return
            elif n == 0xffffffff:
                debug2('bup server: receive-objects suspended.\n')
                self.suspended_w = w
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
                               % git.shorten_hash(name))
                        debug1("bup server:   because of object %s\n"
                               % hexlify(shar))
                        self.conn.write(b'index %s\n' % name)
                        suggested.add(name)
                    continue
            nw, crc = w._raw_write((buf,), sha=shar)
            self._check(w, crcr, crc, 'object read: expected crc %d, got %d\n')
        # NOTREACHED

    def _check(self, w, expected, actual, msg):
        if expected != actual:
            w.abort()
            raise Exception(msg % (expected, actual))

    def _read_ref(self, refname):
        return git.read_ref(refname)

    def _update_ref(self, refname, newval, oldval):
        git.update_ref(refname, newval, oldval)

    def _join(self, id):
        for blob in git.cp().join(id):
            yield blob

    def _cat(self, ref):
        return self.repo.cat(ref)

    def _refs(self, patterns, limit_to_heads, limit_to_tags):
        for name, oid in git.list_refs(patterns=patterns,
                                       limit_to_heads=limit_to_heads,
                                       limit_to_tags=limit_to_tags):
            yield name, oid

    def rev_list(self, _):
        self._init_session()
        count = self.conn.readline()
        if not count:
            raise Exception('Unexpected EOF while reading rev-list count')
        count = None if count == b'\n' else int(count)
        fmt = self.conn.readline()
        if not fmt:
            raise Exception('Unexpected EOF while reading rev-list format')
        fmt = None if fmt == b'\n' else fmt[:-1]
        refs = tuple(x[:-1] for x in lines_until_sentinel(self.conn, b'\n', Exception))
        args = git.rev_list_invocation(refs, count=count, format=fmt)
        p = subprocess.Popen(git.rev_list_invocation(refs, count=count, format=fmt),
                             env=git._gitenv(git.repodir),
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
