
from __future__ import absolute_import
import errno, os, re, struct, sys, time, zlib
import socket

from bup import git, ssh, vfs
from bup.compat import range
from bup.helpers import (Conn, DemuxConn,                         
                         atoi, atomically_replaced_file, chunkyreader, debug1,
                         debug2, linereader, lines_until_sentinel,
                         mkdirp, progress, qprogress)
from bup.vint import read_bvec, read_vuint, write_bvec


bwlimit = None


class ClientError(Exception):
    pass


def _raw_write_bwlimit(f, buf, bwcount, bwtime):
    if not bwlimit:
        f.write(buf)
        return (len(buf), time.time())
    else:
        # We want to write in reasonably large blocks, but not so large that
        # they're likely to overflow a router's queue.  So our bwlimit timing
        # has to be pretty granular.  Also, if it takes too long from one
        # transmit to the next, we can't just make up for lost time to bring
        # the average back up to bwlimit - that will risk overflowing the
        # outbound queue, which defeats the purpose.  So if we fall behind
        # by more than one block delay, we shouldn't ever try to catch up.
        for i in range(0,len(buf),4096):
            now = time.time()
            next = max(now, bwtime + 1.0*bwcount/bwlimit)
            time.sleep(next-now)
            sub = buf[i:i+4096]
            f.write(sub)
            bwcount = len(sub)  # might be less than 4096
            bwtime = next
        return (bwcount, bwtime)


def parse_remote(remote):
    protocol = r'([a-z]+)://'
    host = r'(?P<sb>\[)?((?(sb)[0-9a-f:]+|[^:/]+))(?(sb)\])'
    port = r'(?::(\d+))?'
    path = r'(/.*)?'
    url_match = re.match(
            '%s(?:%s%s)?%s' % (protocol, host, port, path), remote, re.I)
    if url_match:
        if not url_match.group(1) in ('ssh', 'bup', 'file'):
            raise ClientError, 'unexpected protocol: %s' % url_match.group(1)
        return url_match.group(1,3,4,5)
    else:
        rs = remote.split(':', 1)
        if len(rs) == 1 or rs[0] in ('', '-'):
            return 'file', None, None, rs[-1]
        else:
            return 'ssh', rs[0], None, rs[1]


class Client:
    def __init__(self, remote, create=False):
        self._busy = self.conn = None
        self.sock = self.p = self.pout = self.pin = None
        is_reverse = os.environ.get('BUP_SERVER_REVERSE')
        if is_reverse:
            assert(not remote)
            remote = '%s:' % is_reverse
        (self.protocol, self.host, self.port, self.dir) = parse_remote(remote)
        self.cachedir = git.repo('index-cache/%s'
                                 % re.sub(r'[^@\w]', '_', 
                                          "%s:%s" % (self.host, self.dir)))
        if is_reverse:
            self.pout = os.fdopen(3, 'rb')
            self.pin = os.fdopen(4, 'wb')
            self.conn = Conn(self.pout, self.pin)
        else:
            if self.protocol in ('ssh', 'file'):
                try:
                    # FIXME: ssh and file shouldn't use the same module
                    self.p = ssh.connect(self.host, self.port, 'server')
                    self.pout = self.p.stdout
                    self.pin = self.p.stdin
                    self.conn = Conn(self.pout, self.pin)
                except OSError as e:
                    raise ClientError, 'connect: %s' % e, sys.exc_info()[2]
            elif self.protocol == 'bup':
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.host, atoi(self.port) or 1982))
                self.sockw = self.sock.makefile('wb')
                self.conn = DemuxConn(self.sock.fileno(), self.sockw)
        self._available_commands = self._get_available_commands()
        self._require_command('init-dir')
        self._require_command('set-dir')
        if self.dir:
            self.dir = re.sub(r'[\r\n]', ' ', self.dir)
            if create:
                self.conn.write('init-dir %s\n' % self.dir)
            else:
                self.conn.write('set-dir %s\n' % self.dir)
            self.check_ok()
        self.sync_indexes()

    def __del__(self):
        try:
            self.close()
        except IOError as e:
            if e.errno == errno.EPIPE:
                pass
            else:
                raise

    def close(self):
        if self.conn and not self._busy:
            self.conn.write('quit\n')
        if self.pin:
            self.pin.close()
        if self.sock and self.sockw:
            self.sockw.close()
            self.sock.shutdown(socket.SHUT_WR)
        if self.conn:
            self.conn.close()
        if self.pout:
            self.pout.close()
        if self.sock:
            self.sock.close()
        if self.p:
            self.p.wait()
            rv = self.p.wait()
            if rv:
                raise ClientError('server tunnel returned exit code %d' % rv)
        self.conn = None
        self.sock = self.p = self.pin = self.pout = None

    def check_ok(self):
        if self.p:
            rv = self.p.poll()
            if rv != None:
                raise ClientError('server exited unexpectedly with code %r'
                                  % rv)
        try:
            return self.conn.check_ok()
        except Exception as e:
            raise ClientError, e, sys.exc_info()[2]

    def check_busy(self):
        if self._busy:
            raise ClientError('already busy with command %r' % self._busy)
        
    def ensure_busy(self):
        if not self._busy:
            raise ClientError('expected to be busy, but not busy?!')
        
    def _not_busy(self):
        self._busy = None

    def _get_available_commands(self):
        self.check_busy()
        self._busy = 'help'
        conn = self.conn
        conn.write('help\n')
        result = set()
        line = self.conn.readline()
        if not line == 'Commands:\n':
            raise ClientError('unexpected help header ' + repr(line))
        while True:
            line = self.conn.readline()
            if line == '\n':
                break
            if not line.startswith('    '):
                raise ClientError('unexpected help line ' + repr(line))
            cmd = line.strip()
            if not cmd:
                raise ClientError('unexpected help line ' + repr(line))
            result.add(cmd)
        # FIXME: confusing
        not_ok = self.check_ok()
        if not_ok:
            raise not_ok
        self._not_busy()
        return frozenset(result)

    def _require_command(self, name):
        if name not in self._available_commands:
            raise ClientError('server does not appear to provide %s command'
                              % name)

    def sync_indexes(self):
        self._require_command('list-indexes')
        self.check_busy()
        conn = self.conn
        mkdirp(self.cachedir)
        # All cached idxs are extra until proven otherwise
        extra = set()
        for f in os.listdir(self.cachedir):
            debug1('%s\n' % f)
            if f.endswith('.idx'):
                extra.add(f)
        needed = set()
        conn.write('list-indexes\n')
        for line in linereader(conn):
            if not line:
                break
            assert(line.find('/') < 0)
            parts = line.split(' ')
            idx = parts[0]
            if len(parts) == 2 and parts[1] == 'load' and idx not in extra:
                # If the server requests that we load an idx and we don't
                # already have a copy of it, it is needed
                needed.add(idx)
            # Any idx that the server has heard of is proven not extra
            extra.discard(idx)

        self.check_ok()
        debug1('client: removing extra indexes: %s\n' % extra)
        for idx in extra:
            os.unlink(os.path.join(self.cachedir, idx))
        debug1('client: server requested load of: %s\n' % needed)
        for idx in needed:
            self.sync_index(idx)
        git.auto_midx(self.cachedir)

    def sync_index(self, name):
        self._require_command('send-index')
        #debug1('requesting %r\n' % name)
        self.check_busy()
        mkdirp(self.cachedir)
        fn = os.path.join(self.cachedir, name)
        if os.path.exists(fn):
            msg = "won't request existing .idx, try `bup bloom --check %s`" % fn
            raise ClientError(msg)
        self.conn.write('send-index %s\n' % name)
        n = struct.unpack('!I', self.conn.read(4))[0]
        assert(n)
        with atomically_replaced_file(fn, 'w') as f:
            count = 0
            progress('Receiving index from server: %d/%d\r' % (count, n))
            for b in chunkyreader(self.conn, n):
                f.write(b)
                count += len(b)
                qprogress('Receiving index from server: %d/%d\r' % (count, n))
            progress('Receiving index from server: %d/%d, done.\n' % (count, n))
            self.check_ok()

    def _make_objcache(self):
        return git.PackIdxList(self.cachedir)

    def _suggest_packs(self):
        ob = self._busy
        if ob:
            assert(ob == 'receive-objects-v2')
            self.conn.write('\xff\xff\xff\xff')  # suspend receive-objects-v2
        suggested = []
        for line in linereader(self.conn):
            if not line:
                break
            debug2('%s\n' % line)
            if line.startswith('index '):
                idx = line[6:]
                debug1('client: received index suggestion: %s\n'
                       % git.shorten_hash(idx))
                suggested.append(idx)
            else:
                assert(line.endswith('.idx'))
                debug1('client: completed writing pack, idx: %s\n'
                       % git.shorten_hash(line))
                suggested.append(line)
        self.check_ok()
        if ob:
            self._busy = None
        idx = None
        for idx in suggested:
            self.sync_index(idx)
        git.auto_midx(self.cachedir)
        if ob:
            self._busy = ob
            self.conn.write('%s\n' % ob)
        return idx

    def new_packwriter(self, compression_level=1,
                       max_pack_size=None, max_pack_objects=None):
        self._require_command('receive-objects-v2')
        self.check_busy()
        def _set_busy():
            self._busy = 'receive-objects-v2'
            self.conn.write('receive-objects-v2\n')
        return PackWriter_Remote(self.conn,
                                 objcache_maker = self._make_objcache,
                                 suggest_packs = self._suggest_packs,
                                 onopen = _set_busy,
                                 onclose = self._not_busy,
                                 ensure_busy = self.ensure_busy,
                                 compression_level=compression_level,
                                 max_pack_size=max_pack_size,
                                 max_pack_objects=max_pack_objects)

    def read_ref(self, refname):
        self._require_command('read-ref')
        self.check_busy()
        self.conn.write('read-ref %s\n' % refname)
        r = self.conn.readline().strip()
        self.check_ok()
        if r:
            assert(len(r) == 40)   # hexified sha
            return r.decode('hex')
        else:
            return None   # nonexistent ref

    def update_ref(self, refname, newval, oldval):
        self._require_command('update-ref')
        self.check_busy()
        self.conn.write('update-ref %s\n%s\n%s\n' 
                        % (refname, newval.encode('hex'),
                           (oldval or '').encode('hex')))
        self.check_ok()

    def join(self, id):
        self._require_command('join')
        self.check_busy()
        self._busy = 'join'
        # Send 'cat' so we'll work fine with older versions
        self.conn.write('cat %s\n' % re.sub(r'[\n\r]', '_', id))
        while 1:
            sz = struct.unpack('!I', self.conn.read(4))[0]
            if not sz: break
            yield self.conn.read(sz)
        # FIXME: ok to assume the only NotOk is a KerError? (it is true atm)
        e = self.check_ok()
        self._not_busy()
        if e:
            raise KeyError(str(e))

    def cat_batch(self, refs):
        self._require_command('cat-batch')
        self.check_busy()
        self._busy = 'cat-batch'
        conn = self.conn
        conn.write('cat-batch\n')
        # FIXME: do we want (only) binary protocol?
        for ref in refs:
            assert ref
            assert '\n' not in ref
            conn.write(ref)
            conn.write('\n')
        conn.write('\n')
        for ref in refs:
            info = conn.readline()
            if info == 'missing\n':
                yield None, None, None, None
                continue
            if not (info and info.endswith('\n')):
                raise ClientError('Hit EOF while looking for object info: %r'
                                  % info)
            oidx, oid_t, size = info.split(' ')
            size = int(size)
            cr = chunkyreader(conn, size)
            yield oidx, oid_t, size, cr
            detritus = next(cr, None)
            if detritus:
                raise ClientError('unexpected leftover data ' + repr(detritus))
        # FIXME: confusing
        not_ok = self.check_ok()
        if not_ok:
            raise not_ok
        self._not_busy()

    def refs(self, patterns=None, limit_to_heads=False, limit_to_tags=False):
        patterns = patterns or tuple()
        self._require_command('refs')
        self.check_busy()
        self._busy = 'refs'
        conn = self.conn
        conn.write('refs %s %s\n' % (1 if limit_to_heads else 0,
                                     1 if limit_to_tags else 0))
        for pattern in patterns:
            assert '\n' not in pattern
            conn.write(pattern)
            conn.write('\n')
        conn.write('\n')
        for line in lines_until_sentinel(conn, '\n', ClientError):
            line = line[:-1]
            oidx, name = line.split(' ')
            if len(oidx) != 40:
                raise ClientError('Invalid object fingerprint in %r' % line)
            if not name:
                raise ClientError('Invalid reference name in %r' % line)
            yield name, oidx.decode('hex')
        # FIXME: confusing
        not_ok = self.check_ok()
        if not_ok:
            raise not_ok
        self._not_busy()

    def rev_list(self, refs, count=None, parse=None, format=None):
        """See git.rev_list for the general semantics, but note that with the
        current interface, the parse function must be able to handle
        (consume) any blank lines produced by the format because the
        first one received that it doesn't consume will be interpreted
        as a terminator for the entire rev-list result.

        """
        self._require_command('rev-list')
        assert (count is None) or (isinstance(count, Integral))
        if format:
            assert '\n' not in format
            assert parse
        for ref in refs:
            assert ref
            assert '\n' not in ref
        self.check_busy()
        self._busy = 'rev-list'
        conn = self.conn
        conn.write('rev-list\n')
        if count is not None:
            conn.write(str(count))
        conn.write('\n')
        if format:
            conn.write(format)
        conn.write('\n')
        for ref in refs:
            conn.write(ref)
            conn.write('\n')
        conn.write('\n')
        if not format:
            for line in lines_until_sentinel(conn, '\n', ClientError):
                line = line.strip()
                assert len(line) == 40
                yield line
        else:
            for line in lines_until_sentinel(conn, '\n', ClientError):
                if not line.startswith('commit '):
                    raise ClientError('unexpected line ' + repr(line))
                cmt_oidx = line[7:].strip()
                assert len(cmt_oidx) == 40
                yield cmt_oidx, parse(conn)
        # FIXME: confusing
        not_ok = self.check_ok()
        if not_ok:
            raise not_ok
        self._not_busy()

    def resolve(self, path, parent=None, want_meta=True, follow=False):
        self._require_command('resolve')
        self.check_busy()
        self._busy = 'resolve'
        conn = self.conn
        conn.write('resolve %d\n' % ((1 if want_meta else 0)
                                     | (2 if follow else 0)
                                     | (4 if parent else 0)))
        if parent:
            vfs.write_resolution(conn, parent)
        write_bvec(conn, path)
        success = ord(conn.read(1))
        assert success in (0, 1)
        if success:
            result = vfs.read_resolution(conn)
        else:
            result = vfs.read_ioerror(conn)
        # FIXME: confusing
        not_ok = self.check_ok()
        if not_ok:
            raise not_ok
        self._not_busy()
        if isinstance(result, vfs.IOError):
            raise result
        return result


class PackWriter_Remote(git.PackWriter):
    def __init__(self, conn, objcache_maker, suggest_packs,
                 onopen, onclose,
                 ensure_busy,
                 compression_level=1,
                 max_pack_size=None,
                 max_pack_objects=None):
        git.PackWriter.__init__(self,
                                objcache_maker=objcache_maker,
                                compression_level=compression_level,
                                max_pack_size=max_pack_size,
                                max_pack_objects=max_pack_objects)
        self.file = conn
        self.filename = 'remote socket'
        self.suggest_packs = suggest_packs
        self.onopen = onopen
        self.onclose = onclose
        self.ensure_busy = ensure_busy
        self._packopen = False
        self._bwcount = 0
        self._bwtime = time.time()

    def _open(self):
        if not self._packopen:
            self.onopen()
            self._packopen = True

    def _end(self, run_midx=True):
        assert(run_midx)  # We don't support this via remote yet
        if self._packopen and self.file:
            self.file.write('\0\0\0\0')
            self._packopen = False
            self.onclose() # Unbusy
            self.objcache = None
            return self.suggest_packs() # Returns last idx received

    def close(self):
        id = self._end()
        self.file = None
        return id

    def abort(self):
        raise ClientError("don't know how to abort remote pack writing")

    def _raw_write(self, datalist, sha):
        assert(self.file)
        if not self._packopen:
            self._open()
        self.ensure_busy()
        data = ''.join(datalist)
        assert(data)
        assert(sha)
        crc = zlib.crc32(data) & 0xffffffff
        outbuf = ''.join((struct.pack('!I', len(data) + 20 + 4),
                          sha,
                          struct.pack('!I', crc),
                          data))
        try:
            (self._bwcount, self._bwtime) = _raw_write_bwlimit(
                    self.file, outbuf, self._bwcount, self._bwtime)
        except IOError as e:
            raise ClientError, e, sys.exc_info()[2]
        self.outbytes += len(data)
        self.count += 1

        if self.file.has_input():
            self.suggest_packs()
            self.objcache.refresh()

        return sha, crc
