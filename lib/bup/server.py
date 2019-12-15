
import os, struct, subprocess
from binascii import hexlify, unhexlify
from contextlib import contextmanager

from bup import git, vfs, vint
from bup.compat import hexstr
from bup.helpers import (debug1, debug2, linereader, lines_until_sentinel, log, pending_raise)
from bup.repo import LocalRepo
from bup.vint import write_vuint

def _command(fn):
    fn.bup_server_command = True
    return fn

class BupProtocolServer:
    def __init__(self, conn, backend):
        self.conn = conn
        self._backend = backend
        self._commands = self._get_commands()
        self.suspended_w = None
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

    def init_session(self, repo_dir=None, init=False):
        if self.repo:
            self.repo.close()
        self.repo = self._backend(repo_dir, init=init)
        debug1('bup server: bupdir is %r\n' % self.repo.repo_dir)
        debug1('bup server: serving in %s mode\n'
               % (self.repo.dumb_server_mode and 'dumb' or 'smart'))

    @_command
    def init_dir(self, arg):
        self.init_session(arg, init=True)
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

    @_command
    def send_index(self, name):
        self.init_session()
        assert(name.find(b'/') < 0)
        assert(name.endswith(b'.idx'))
        with self.repo.send_index(name) as data:
            self.conn.write(struct.pack('!I', len(data)))
            self.conn.write(data)
        self.conn.ok()

    def _check(self, w, expected, actual, msg):
        if expected != actual:
            w.abort()
            raise Exception(msg % (expected, actual))

    @_command
    def receive_objects_v2(self, junk):
        self.init_session()
        if self.suspended_w:
            w = self.suspended_w
            self.suspended_w = None
        else:
            w = self.repo.new_packwriter()
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
                if not self.repo.dumb_server_mode:
                    oldpack = w.exists(shar, want_source=True)
                    if oldpack:
                        assert(not oldpack == True)
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
            log('server: error: %s\n' % str(e).encode('utf-8'))
            self.conn.write(b'\0\0\0\0')
            self.conn.error(e)
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
            self.conn.write(b'\n')
            self.conn.error(str(e).encode('ascii'))
            raise

    @_command
    def resolve(self, args):
        self.init_session()
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
            res = list(self.repo.resolve(path, parent, want_meta, follow))
        except vfs.IOError as ex:
            res = ex
        if isinstance(res, vfs.IOError):
            self.conn.write(b'\0')  # error
            vfs.write_ioerror(self.conn, res)
        else:
            self.conn.write(b'\1')  # success
            vfs.write_resolution(self.conn, res)
        self.conn.ok()

    @_command
    def config_get(self, args):
        self.init_session()
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
        with pending_raise(value, rethrow=False):
            if self.suspended_w:
                self.suspended_w.close()
            if self.repo:
                self.repo.close()

class AbstractServerBackend(object):
    '''
    This is an abstract base class for the server backend which
    really just serves for documentation purposes, you don't even
    need to inherit a backend from this.
    '''
    def __init__(self, repo_dir=None, init=False):
        self.dumb_server_mode = False

    def list_indexes(self):
        """
        This should return a list of or be an iterator listing all
        the indexes present in the repository.
        """
        raise NotImplementedError('Subclasses must implement list_indexes')

    def send_index(self, name):
        """
        This should return a context manager memory object whose len() can
        be determined and that can be written to the connection.
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

    def rev_list_raw(self, refs, fmt):
        """
        Yield chunks of data to send to the client containing the
        git rev-list output for the given arguments.
        """
        raise NotImplementedError("Subclasses must implement rev_list_raw")

    def resolve(self, path, parent, want_meta, follow):
        """
        Return a list (or yield entries, but we convert to a list) of VFS
        resolutions given the arguments. May raise vfs.IOError to indicate
        errors happened.
        """
        raise NotImplementedError("Subclasses must implement resolve")

    def close(self):
        """
        Close the underlying backend/repository.
        """
        raise NotImplemented("Subclasses must implement close")

class GitServerBackend(AbstractServerBackend):
    def __init__(self, repo_dir=None, init=False):
        super(GitServerBackend, self).__init__(repo_dir, init)
        if init:
            git.init_repo(repo_dir)
            debug1('bup server: bupdir initialized: %r\n' % git.repodir)
        git.check_repo_or_die(repo_dir)
        self.repo = LocalRepo(repo_dir)
        self.repo_dir = self.repo.repo_dir
        self.dumb_server_mode = os.path.exists(git.repo(b'bup-dumb-server'))
        self.update_ref = self.repo.update_ref
        self.join = self.repo.join
        self.cat = self.repo.cat
        self.refs = self.repo.refs
        self.resolve = self.repo.resolve

    def close(self):
        if self.repo:
            self.repo.close()
            self.repo = None

    def list_indexes(self):
        for f in os.listdir(git.repo(b'objects/pack')):
            yield f

    @contextmanager
    def send_index(self, name):
        with git.open_idx(git.repo(b'objects/pack/%s' % name)) as idx:
            yield idx.map

    def new_packwriter(self):
        if self.dumb_server_mode:
            return git.PackWriter(objcache_maker=None, run_midx=False)
        return git.PackWriter()

    def read_ref(self, refname):
        return git.read_ref(refname)

    def rev_list_raw(self, refs, fmt):
        args = git.rev_list_invocation(refs, format=fmt)
        p = subprocess.Popen(args, env=git._gitenv(git.repodir),
                             stdout=subprocess.PIPE)
        while True:
            out = p.stdout.read(64 * 1024)
            if not out:
                break
            yield out
        rv = p.wait()  # not fatal
        if rv:
            raise git.GitError('git rev-list returned error %d' % rv)

    def config_get(self, key, opttype):
        return git.git_config_get(key, opttype=opttype)
