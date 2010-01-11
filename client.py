import re, struct, errno
import git
from helpers import *
from subprocess import Popen, PIPE

class ClientError(Exception):
    pass

class Client:
    def __init__(self, remote, create=False):
        self._busy = None
        self._indexes_synced = 0
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
            self.conn.check_ok()
        except Exception, e:
            raise ClientError, e, sys.exc_info()[2]

    def check_busy(self):
        if self._busy:
            raise ClientError('already busy with command %r' % self._busy)
        
    def _not_busy(self):
        self._busy = None

    def sync_indexes(self):
        self.check_busy()
        conn = self.conn
        conn.write('list-indexes\n')
        packdir = git.repo('objects/pack')
        mkdirp(self.cachedir)
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

        for f in os.listdir(self.cachedir):
            if f.endswith('.idx') and not f in all:
                log('pruning old index: %r\n' % f)
                os.unlink(os.path.join(self.cachedir, f))

        # FIXME this should be pipelined: request multiple indexes at a time, or
        # we waste lots of network turnarounds.
        for name in needed.keys():
            log('requesting %r\n' % name)
            conn.write('send-index %s\n' % name)
            n = struct.unpack('!I', conn.read(4))[0]
            assert(n)
            log('   expect %d bytes\n' % n)
            fn = os.path.join(self.cachedir, name)
            f = open(fn + '.tmp', 'w')
            for b in chunkyreader(conn, n):
                f.write(b)
            self.check_ok()
            f.close()
            os.rename(fn + '.tmp', fn)

        self._indexes_synced = 1

    def _make_objcache(self):
        ob = self._busy
        self._busy = None
        self.sync_indexes()
        self._busy = ob
        return git.MultiPackIndex(self.cachedir)

    def new_packwriter(self):
        self.check_busy()
        self._busy = 'receive-objects'
        return PackWriter_Remote(self.conn,
                                 objcache_maker = self._make_objcache,
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
        self.check_ok()
        self._not_busy()


class PackWriter_Remote(git.PackWriter):
    def __init__(self, conn, objcache_maker=None, onclose=None):
        git.PackWriter.__init__(self, objcache_maker)
        self.file = conn
        self.filename = 'remote socket'
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
            id = self.file.readline().strip()
            self.file.check_ok()
            self.objcache = None
            if self.onclose:
                self.onclose()
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


