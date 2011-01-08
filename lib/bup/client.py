import re, struct, errno, time, zlib
from bup import git, ssh
from bup.helpers import *

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
        for i in xrange(0,len(buf),4096):
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
        assert(url_match.group(1) in ('ssh', 'bup', 'file'))
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
        else:
            if self.protocol in ('ssh', 'file'):
                try:
                    # FIXME: ssh and file shouldn't use the same module
                    self.p = ssh.connect(self.host, self.port, 'server')
                    self.pout = self.p.stdout
                    self.pin = self.p.stdin
                except OSError, e:
                    raise ClientError, 'connect: %s' % e, sys.exc_info()[2]
            elif self.protocol == 'bup':
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.host, self.port or 1982))
                self.pout = self.sock.makefile('rb')
                self.pin = self.sock.makefile('wb')
        self.conn = Conn(self.pout, self.pin)
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
        except IOError, e:
            if e.errno == errno.EPIPE:
                pass
            else:
                raise

    def close(self):
        if self.conn and not self._busy:
            self.conn.write('quit\n')
        if self.pin and self.pout:
            self.pin.close()
            while self.pout.read(65536):
                pass
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
        except Exception, e:
            raise ClientError, e, sys.exc_info()[2]

    def check_busy(self):
        if self._busy:
            raise ClientError('already busy with command %r' % self._busy)
        
    def ensure_busy(self):
        if not self._busy:
            raise ClientError('expected to be busy, but not busy?!')
        
    def _not_busy(self):
        self._busy = None

    def sync_indexes(self):
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

    def sync_index(self, name):
        #debug1('requesting %r\n' % name)
        self.check_busy()
        mkdirp(self.cachedir)
        self.conn.write('send-index %s\n' % name)
        n = struct.unpack('!I', self.conn.read(4))[0]
        assert(n)
        fn = os.path.join(self.cachedir, name)
        f = open(fn + '.tmp', 'w')
        count = 0
        progress('Receiving index from server: %d/%d\r' % (count, n))
        for b in chunkyreader(self.conn, n):
            f.write(b)
            count += len(b)
            progress('Receiving index from server: %d/%d\r' % (count, n))
        progress('Receiving index from server: %d/%d, done.\n' % (count, n))
        self.check_ok()
        f.close()
        os.rename(fn + '.tmp', fn)
        git.auto_midx(self.cachedir)

    def _make_objcache(self):
        return git.PackIdxList(self.cachedir)

    def _suggest_pack(self, indexname):
        debug1('client: received index suggestion: %s\n' % indexname)
        ob = self._busy
        if ob:
            assert(ob == 'receive-objects-v2')
            self.conn.write('\xff\xff\xff\xff')  # suspend receive-objects
            self._busy = None
            self.conn.drain_and_check_ok()
        self.sync_index(indexname)
        if ob:
            self._busy = ob
            self.conn.write('receive-objects-v2\n')

    def new_packwriter(self):
        self.check_busy()
        def _set_busy():
            self._busy = 'receive-objects-v2'
            self.conn.write('receive-objects-v2\n')
        return PackWriter_Remote(self.conn,
                                 objcache_maker = self._make_objcache,
                                 suggest_pack = self._suggest_pack,
                                 onopen = _set_busy,
                                 onclose = self._not_busy,
                                 ensure_busy = self.ensure_busy)

    def read_ref(self, refname):
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
        self.check_busy()
        self.conn.write('update-ref %s\n%s\n%s\n' 
                        % (refname, newval.encode('hex'),
                           (oldval or '').encode('hex')))
        self.check_ok()

    def cat(self, id):
        self.check_busy()
        self._busy = 'cat'
        self.conn.write('cat %s\n' % re.sub(r'[\n\r]', '_', id))
        while 1:
            sz = struct.unpack('!I', self.conn.read(4))[0]
            if not sz: break
            yield self.conn.read(sz)
        e = self.check_ok()
        self._not_busy()
        if e:
            raise KeyError(str(e))


class PackWriter_Remote(git.PackWriter):
    def __init__(self, conn, objcache_maker, suggest_pack,
                 onopen, onclose,
                 ensure_busy):
        git.PackWriter.__init__(self, objcache_maker)
        self.file = conn
        self.filename = 'remote socket'
        self.suggest_pack = suggest_pack
        self.onopen = onopen
        self.onclose = onclose
        self.ensure_busy = ensure_busy
        self._packopen = False
        self._bwcount = 0
        self._bwtime = time.time()

    def _open(self):
        if not self._packopen:
            if self.onopen:
                self.onopen()
            self._packopen = True

    def _end(self):
        if self._packopen and self.file:
            self.file.write('\0\0\0\0')
            self._packopen = False
            while True:
                line = self.file.readline().strip()
                if line.startswith('index '):
                    pass
                else:
                    break
            id = line
            self.file.check_ok()
            self.objcache = None
            if self.onclose:
                self.onclose()
            if id and self.suggest_pack:
                self.suggest_pack(id)
            return id

    def close(self):
        id = self._end()
        self.file = None
        return id

    def abort(self):
        raise GitError("don't know how to abort remote pack writing")

    def _raw_write(self, datalist, sha):
        assert(self.file)
        if not self._packopen:
            self._open()
        if self.ensure_busy:
            self.ensure_busy()
        data = ''.join(datalist)
        assert(data)
        assert(sha)
        crc = zlib.crc32(data) & 0xffffffff
        outbuf = ''.join((struct.pack('!I', len(data) + 20 + 4),
                          sha,
                          struct.pack('!I', crc),
                          data))
        (self._bwcount, self._bwtime) = \
            _raw_write_bwlimit(self.file, outbuf, self._bwcount, self._bwtime)
        self.outbytes += len(data) - 20 - 4 # Don't count sha1+crc
        self.count += 1

        if self.file.has_input():
            line = self.file.readline().strip()
            assert(line.startswith('index '))
            idxname = line[6:]
            if self.suggest_pack:
                self.suggest_pack(idxname)
                self.objcache.refresh()

        return sha, crc
