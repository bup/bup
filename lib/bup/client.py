import re, struct, errno, select
from bup import git
from bup.helpers import *
from subprocess import Popen, PIPE


class ClientError(Exception):
    pass


class Client:
    def __init__(self, remote, create=False):
        self._busy = None
        self.p = None
        self.conn = None
        rs = remote.split(':', 1)
        nicedir = os.path.split(os.path.abspath(sys.argv[0]))[0]
        nicedir = re.sub(r':', "_", nicedir)
        if len(rs) == 1:
            (host, dir) = ('NONE', remote)
            def fixenv():
                os.environ['PATH'] = ':'.join([nicedir,
                                               os.environ.get('PATH', '')])
            argv = ['bup', 'server']
        else:
            (host, dir) = rs
            fixenv = None
            # WARNING: shell quoting security holes are possible here, so we
            # have to be super careful.  We have to use 'sh -c' because
            # csh-derived shells can't handle PATH= notation.  We can't
            # set PATH in advance, because ssh probably replaces it.  We
            # can't exec *safely* using argv, because *both* ssh and 'sh -c'
            # allow shellquoting.  So we end up having to double-shellquote
            # stuff here.
            escapedir = re.sub(r'([^\w/])', r'\\\\\\\1', nicedir)
            cmd = r"""
                       sh -c PATH=%s:'$PATH bup server'
                   """ % escapedir
            argv = ['ssh', host, '--', cmd.strip()]
            #log('argv is: %r\n' % argv)
        (self.host, self.dir) = (host, dir)
        self.cachedir = git.repo('index-cache/%s'
                                 % re.sub(r'[^@\w]', '_', 
                                          "%s:%s" % (host, dir)))
        try:
            self.p = p = Popen(argv, stdin=PIPE, stdout=PIPE, preexec_fn=fixenv)
        except OSError, e:
            raise ClientError, 'exec %r: %s' % (argv[0], e), sys.exc_info()[2]
        self.conn = conn = Conn(p.stdout, p.stdin)
        if dir:
            dir = re.sub(r'[\r\n]', ' ', dir)
            if create:
                conn.write('init-dir %s\n' % dir)
            else:
                conn.write('set-dir %s\n' % dir)
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
        if self.p:
            self.p.stdin.close()
            while self.p.stdout.read(65536):
                pass
            self.p.stdout.close()
            self.p.wait()
            rv = self.p.wait()
            if rv:
                raise ClientError('server tunnel returned exit code %d' % rv)
        self.conn = None
        self.p = None

    def check_ok(self):
        rv = self.p.poll()
        if rv != None:
            raise ClientError('server exited unexpectedly with code %r' % rv)
        try:
            return self.conn.check_ok()
        except Exception, e:
            raise ClientError, e, sys.exc_info()[2]

    def check_busy(self):
        if self._busy:
            raise ClientError('already busy with command %r' % self._busy)
        
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
        return git.MultiPackIndex(self.cachedir)

    def _suggest_pack(self, indexname):
        log('received index suggestion: %s\n' % indexname)
        ob = self._busy
        if ob:
            assert(ob == 'receive-objects')
            self._busy = None
            self.conn.write('\xff\xff\xff\xff')  # suspend receive-objects
            self.conn.drain_and_check_ok()
        self.sync_index(indexname)
        if ob:
            self.conn.write('receive-objects\n')
            self._busy = ob

    def new_packwriter(self):
        self.check_busy()
        self._busy = 'receive-objects'
        return PackWriter_Remote(self.conn,
                                 objcache_maker = self._make_objcache,
                                 suggest_pack = self._suggest_pack,
                                 onclose = self._not_busy)

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
    def __init__(self, conn, objcache_maker, suggest_pack, onclose):
        git.PackWriter.__init__(self, objcache_maker)
        self.file = conn
        self.filename = 'remote socket'
        self.suggest_pack = suggest_pack
        self.onclose = onclose
        self._packopen = False

    def _open(self):
        if not self._packopen:
            self._make_objcache()
            self.file.write('receive-objects\n')
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
            if self.suggest_pack:
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
