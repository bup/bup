from __future__ import absolute_import
import os, struct, subprocess
from binascii import hexlify, unhexlify

from bup import git, vfs, vint
from bup.compat import environ, hexstr, int_types
from bup.io import byte_stream, path_msg
from bup.git import MissingObject
from bup.helpers import (debug1, debug2, linereader, lines_until_sentinel, log)
from bup.repo import LocalRepo


class BupProtocolServer:
    def __init__(self, conn, backend):
        self.conn = conn
        self._backend = backend
        self.suspended_w = None
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

    def init_dir(self, arg):
        self._backend.init_dir(arg)
        self._backend.init_session(arg)
        self.conn.ok()

    def set_dir(self, arg):
        self._backend.init_session(arg)
        self.conn.ok()

    def list_indexes(self, junk):
        self._backend.init_session()
        suffix = b' load' if self._backend.dumb_server_mode else b''
        for f in self._backend.list_indexes():
            # must end with .idx to not confuse everything, so filter
            # here ... even if the subclass might not yield anything
            # else to start with
            if f.endswith(b'.idx'):
                self.conn.write(b'%s%s\n' % (f, suffix))
        self.conn.ok()

    def send_index(self, name):
        self._backend.init_session()
        assert(name.find(b'/') < 0)
        assert(name.endswith(b'.idx'))
        data = self._backend.send_index(name)
        self.conn.write(struct.pack('!I', len(data)))
        self.conn.write(data)
        self.conn.ok()

    def _check(self, w, expected, actual, msg):
        if expected != actual:
            w.abort()
            raise Exception(msg % (expected, actual))

    def receive_objects_v2(self, junk):
        self._backend.init_session()
        suggested = set()
        if self.suspended_w:
            w = self.suspended_w
            self.suspended_w = None
        else:
            w = self._backend.new_packwriter()
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
                fullpath = w.close(run_midx=not self._backend.dumb_server_mode)
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
            if not self._backend.dumb_server_mode:
                oldpack = w.exists(shar, want_source=True)
                if oldpack:
                    assert(not oldpack == True)
                    assert(oldpack.endswith(b'.idx'))
                    (dir,name) = os.path.split(oldpack)
                    if not (name in suggested):
                        debug1("bup server: suggesting index %s\n"
                               % git.shorten_hash(name))
                        debug1("bup server:   because of object %s\n"
                               % hexstr(shar))
                        self.conn.write(b'index %s\n' % name)
                        suggested.add(name)
                    continue
            nw, crc = w._raw_write((buf,), sha=shar)
            self._check(w, crcr, crc, 'object read: expected crc %d, got %d\n')
        # NOTREACHED

    def read_ref(self, refname):
        self._backend.init_session()
        r = self._backend.read_ref(refname)
        self.conn.write(b'%s\n' % hexlify(r or b''))
        self.conn.ok()

    def update_ref(self, refname):
        self._backend.init_session()
        newval = self.conn.readline().strip()
        oldval = self.conn.readline().strip()
        self._backend.update_ref(refname, unhexlify(newval), unhexlify(oldval))
        self.conn.ok()

    def join(self, id):
        self._backend.init_session()
        try:
            for blob in self._backend.join(id):
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

    def cat_batch(self, dummy):
        self._backend.init_session()
        # For now, avoid potential deadlock by just reading them all
        for ref in tuple(lines_until_sentinel(self.conn, b'\n', Exception)):
            ref = ref[:-1]
            it = self._backend.cat(ref)
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
        self._backend.init_session()
        patterns = tuple(x[:-1] for x in lines_until_sentinel(self.conn, b'\n', Exception))
        for name, oid in self._backend.refs(patterns, limit_to_heads, limit_to_tags):
            assert b'\n' not in name
            self.conn.write(b'%s %s\n' % (hexlify(oid), name))
        self.conn.write(b'\n')
        self.conn.ok()

    def rev_list(self, _):
        self._backend.init_session()
        count = self.conn.readline()
        if not count:
            raise Exception('Unexpected EOF while reading rev-list count')
        count = None if count == b'\n' else int(count)
        fmt = self.conn.readline()
        if not fmt:
            raise Exception('Unexpected EOF while reading rev-list format')
        fmt = None if fmt == b'\n' else fmt[:-1]
        refs = tuple(x[:-1] for x in lines_until_sentinel(self.conn, b'\n', Exception))

        try:
            for buf in self._backend.rev_list(refs, count, fmt):
                self.conn.write(buf)
            self.conn.write(b'\n')
            self.conn.ok()
        except git.GitError as e:
            self.conn.write(b'\n')
            self.conn.error(str(e).encode('ascii'))
            raise

    def resolve(self, args):
        self._backend.init_session()
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
            res = list(self._backend.resolve(path, parent, want_meta, follow))
        except vfs.IOError as ex:
            res = ex
        if isinstance(res, vfs.IOError):
            self.conn.write(b'\0')  # error
            vfs.write_ioerror(self.conn, res)
        else:
            self.conn.write(b'\1')  # success
            vfs.write_resolution(self.conn, res)
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
            fn = getattr(self, cmdattr, None)
            if not cmd in commands or not callable(fn):
                raise Exception('unknown server command: %r\n' % line)
            fn(rest)

        debug1('bup server: done\n')

class AbstractServerBackend(object):
    '''
    This is an abstract base class for the server backend which
    really just serves for documentation purposes, you don't even
    need to inherit a backend from this.
    '''
    def __init__(self):
        self.dumb_server_mode = False

    def init_session(self, reinit_with_new_repopath=None):
        raise NotImplementedError("Subclasses must implement init_session")

    def init_dir(self, arg):
        raise NotImplementedError("Subclasses must implement init_dir")

    def list_indexes(self):
        """
        This should return a list of or be an iterator listing all
        the indexes present in the repository.
        """
        raise NotImplementedError('Subclasses must implement list_indexes')

    def send_index(self, name):
        """
        This should return a memory object whose len() can be determined
        and that can be written to the connection.
        """
        raise NotImplementedError("Subclasses must implement send_index")

    def new_packwriter(self):
        """
        Return an object implementing the PackWriter protocol.
        """
        raise NotImplementedError("Subclasses must implement new_packwriter")

    def read_ref(self, refname):
        raise NotImplementedError("Subclasses must implement read_ref")

    def update_ref(self, refname, newval, oldval):
        """
        This updates the given ref from the old to the new value.
        """
        raise NotImplementedError("Subclasses must implemented update_ref")

    def join(self, id):
        """
        This should yield all the blob data for the given id,
        may raise KeyError if not present.
        """
        raise NotImplementedError("Subclasses must implemented join")

    def cat(self, ref):
        """
        Retrieve one ref. This must return an iterator that yields
        (oidx, type, size), followed by the data referred to by ref,
        or only (None, None, None) if the ref doesn't exist.
        """
        raise NotImplementedError("Subclasses must implement cat")

    def refs(self, patterns, limit_to_heads, limit_to_tags):
        """
        This should yield (name, oid) tuples according to the configuration
        passed in the arguments.
        """
        raise NotImplementedError("Subclasses must implement refs")

    def rev_list(self, refs, count, fmt):
        """
        Yield chunks of data to send to the client containing the
        git rev-list output for the given arguments.
        """
        raise NotImplementedError("Subclasses must implement rev_list")

    def resolve(self, path, parent, want_meta, follow):
        """
        Return a list (or yield entries, but we convert to a list) of VFS
        resolutions given the arguments. May raise vfs.IOError to indicate
        errors happened.
        """
        raise NotImplementedError("Subclasses must implement resolve")


class GitServerBackend(AbstractServerBackend):
    def __init__(self):
        super(GitServerBackend, self).__init__()
        self.repo = None

    def _set_mode(self):
        self.dumb_server_mode = os.path.exists(git.repo(b'bup-dumb-server'))
        debug1('bup server: serving in %s mode\n'
               % (self.dumb_server_mode and 'dumb' or 'smart'))

    def init_session(self, reinit_with_new_repopath=None):
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

    def init_dir(self, arg):
        git.init_repo(arg)
        debug1('bup server: bupdir initialized: %s\n' % path_msg(git.repodir))

    def list_indexes(self):
        for f in os.listdir(git.repo(b'objects/pack')):
            yield f

    def send_index(self, name):
        return git.open_idx(git.repo(b'objects/pack/%s' % name)).map

    def new_packwriter(self):
        if self.dumb_server_mode:
            return git.PackWriter(objcache_maker=None)
        return git.PackWriter()

    def read_ref(self, refname):
        return git.read_ref(refname)

    def update_ref(self, refname, newval, oldval):
        git.update_ref(refname, newval, oldval)

    def join(self, id):
        for blob in git.cp().join(id):
            yield blob

    def cat(self, ref):
        return self.repo.cat(ref)

    def refs(self, patterns, limit_to_heads, limit_to_tags):
        for name, oid in git.list_refs(patterns=patterns,
                                       limit_to_heads=limit_to_heads,
                                       limit_to_tags=limit_to_tags):
            yield name, oid

    def rev_list(self, refs, count, fmt):
        args = git.rev_list_invocation(refs, count=count, format=fmt)
        p = subprocess.Popen(git.rev_list_invocation(refs, count=count, format=fmt),
                             env=git._gitenv(git.repodir),
                             stdout=subprocess.PIPE)
        while True:
            out = p.stdout.read(64 * 1024)
            if not out:
                break
            yield out
        rv = p.wait()  # not fatal
        if rv:
            raise git.GitError('git rev-list returned error %d' % rv)

    def resolve(self, path, parent, want_meta, follow):
        return vfs.resolve(self.repo, path, parent=parent, want_meta=want_meta,
                           follow=follow)
