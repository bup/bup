import re, struct, errno, select
from bup import git, ssh
from bup.helpers import *


class ClientError(Exception):
    pass


class Client:
    def __init__(self, remote, create=False):
        self._busy = self.conn = self.p = self.pout = self.pin = None
        is_reverse = os.environ.get('BUP_SERVER_REVERSE')
        if is_reverse:
            assert(not remote)
            remote = '%s:' % is_reverse
        rs = remote.split(':', 1)
        if len(rs) == 1:
            (host, dir) = (None, remote)
        else:
            (host, dir) = rs
        (self.host, self.dir) = (host, dir)
        self.cachedir = git.repo('index-cache/%s'
                                 % re.sub(r'[^@\w]', '_', 
                                          "%s:%s" % (host, dir)))
        try:
            if is_reverse:
                self.pout = os.fdopen(3, 'rb')
                self.pin = os.fdopen(4, 'wb')
            else:
                self.p = ssh.connect(host, 'server')
                self.pout = self.p.stdout
                self.pin = self.p.stdin
        except OSError, e:
            raise ClientError, 'exec %r: %s' % (argv[0], e), sys.exc_info()[2]
        self.conn = Conn(self.pout, self.pin)
        if dir:
            dir = re.sub(r'[\r\n]', ' ', dir)
            if create:
                self.conn.write('init-dir %s\n' % dir)
            else:
                self.conn.write('set-dir %s\n' % dir)
            self.check_ok()
        self.sync_indexes_del()

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
        if self.p:
            self.p.wait()
            rv = self.p.wait()
            if rv:
                raise ClientError('server tunnel returned exit code %d' % rv)
        self.conn = None
        self.p = self.pin = self.pout = None

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

    def sync_indexes_del(self):
        self.check_busy()
        conn = self.conn
        conn.write('list-indexes\n')
        packdir = git.repo('objects/pack')
        all = {}
        needed = {}
        for line in linereader(conn):
            if not line:
                break
            all[line] = 1
            assert(line.find('/') < 0)
            if not os.path.exists(os.path.join(self.cachedir, line)):
                needed[line] = 1
        self.check_ok()

        mkdirp(self.cachedir)
        for f in os.listdir(self.cachedir):
            if f.endswith('.idx') and not f in all:
                log('pruning old index: %r\n' % f)
                os.unlink(os.path.join(self.cachedir, f))

    def sync_index(self, name):
        #log('requesting %r\n' % name)
        self.check_busy()
        mkdirp(self.cachedir)
        self.conn.write('send-index %s\n' % name)
        n = struct.unpack('!I', self.conn.read(4))[0]
        assert(n)
        fn = os.path.join(self.cachedir, name)
        f = open(fn + '.tmp', 'w')
        count = 0
        progress('Receiving index: %d/%d\r' % (count, n))
        for b in chunkyreader(self.conn, n):
            f.write(b)
            count += len(b)
            progress('Receiving index: %d/%d\r' % (count, n))
        progress('Receiving index: %d/%d, done.\n' % (count, n))
        self.check_ok()
        f.close()
        os.rename(fn + '.tmp', fn)

    def _make_objcache(self):
        ob = self._busy
        self._busy = None
        #self.sync_indexes()
        self._busy = ob
        return git.PackIdxList(self.cachedir)

    def _suggest_pack(self, indexname):
        log('received index suggestion: %s\n' % indexname)
        ob = self._busy
        if ob:
            assert(ob == 'receive-objects')
            self.conn.write('\xff\xff\xff\xff')  # suspend receive-objects
            self._busy = None
            self.conn.drain_and_check_ok()
        self.sync_index(indexname)
        if ob:
            self._busy = ob
            self.conn.write('receive-objects\n')

    def new_packwriter(self):
        self.check_busy()
        def _set_busy():
            self._busy = 'receive-objects'
            self.conn.write('receive-objects\n')
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

    def _open(self):
        if not self._packopen:
            self._make_objcache()
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

    def _raw_write(self, datalist):
        assert(self.file)
        if not self._packopen:
            self._open()
        if self.ensure_busy:
            self.ensure_busy()
        data = ''.join(datalist)
        assert(len(data))
        self.file.write(struct.pack('!I', len(data)) + data)
        self.outbytes += len(data)
        self.count += 1

        if self.file.has_input():
            line = self.file.readline().strip()
            assert(line.startswith('index '))
            idxname = line[6:]
            if self.suggest_pack:
                self.suggest_pack(idxname)
                self.objcache.refresh()
