import sys, os, pwd, subprocess, errno, socket, select, mmap, stat, re


# Write (blockingly) to sockets that may or may not be in blocking mode.
# We need this because our stderr is sometimes eaten by subprocesses
# (probably ssh) that sometimes make it nonblocking, if only temporarily,
# leading to race conditions.  Ick.  We'll do it the hard way.
def _hard_write(fd, buf):
    while buf:
        (r,w,x) = select.select([], [fd], [], None)
        if not w:
            raise IOError('select(fd) returned without being writable')
        try:
            sz = os.write(fd, buf)
        except OSError, e:
            if e.errno != errno.EAGAIN:
                raise
        assert(sz >= 0)
        buf = buf[sz:]

def log(s):
    _hard_write(sys.stderr.fileno(), s)


def mkdirp(d):
    try:
        os.makedirs(d)
    except OSError, e:
        if e.errno == errno.EEXIST:
            pass
        else:
            raise


def next(it):
    try:
        return it.next()
    except StopIteration:
        return None
    
    
def unlink(f):
    try:
        os.unlink(f)
    except OSError, e:
        if e.errno == errno.ENOENT:
            pass  # it doesn't exist, that's what you asked for


def readpipe(argv):
    p = subprocess.Popen(argv, stdout=subprocess.PIPE)
    r = p.stdout.read()
    p.wait()
    return r


# FIXME: this function isn't very generic, because it splits the filename
# in an odd way and depends on a terminating '/' to indicate directories.
# But it's used in a couple of places, so let's put it here.
def pathsplit(p):
    l = p.split('/')
    l = [i+'/' for i in l[:-1]] + l[-1:]
    if l[-1] == '':
        l.pop()  # extra blank caused by terminating '/'
    return l


# like os.path.realpath, but doesn't follow a symlink for the last element.
# (ie. if 'p' itself is itself a symlink, this one won't follow it)
def realpath(p):
    try:
        st = os.lstat(p)
    except OSError:
        st = None
    if st and stat.S_ISLNK(st.st_mode):
        (dir, name) = os.path.split(p)
        dir = os.path.realpath(dir)
        out = os.path.join(dir, name)
    else:
        out = os.path.realpath(p)
    #log('realpathing:%r,%r\n' % (p, out))
    return out


_username = None
def username():
    global _username
    if not _username:
        uid = os.getuid()
        try:
            _username = pwd.getpwuid(uid)[0]
        except KeyError:
            _username = 'user%d' % uid
    return _username


_userfullname = None
def userfullname():
    global _userfullname
    if not _userfullname:
        uid = os.getuid()
        try:
            _userfullname = pwd.getpwuid(uid)[4].split(',')[0]
        except KeyError:
            _userfullname = 'user%d' % uid
    return _userfullname


_hostname = None
def hostname():
    global _hostname
    if not _hostname:
        _hostname = socket.getfqdn()
    return _hostname


class NotOk(Exception):
    pass

class Conn:
    def __init__(self, inp, outp):
        self.inp = inp
        self.outp = outp

    def read(self, size):
        self.outp.flush()
        return self.inp.read(size)

    def readline(self):
        self.outp.flush()
        return self.inp.readline()

    def write(self, data):
        #log('%d writing: %d bytes\n' % (os.getpid(), len(data)))
        self.outp.write(data)

    def has_input(self):
        [rl, wl, xl] = select.select([self.inp.fileno()], [], [], 0)
        if rl:
            assert(rl[0] == self.inp.fileno())
            return True
        else:
            return None

    def ok(self):
        self.write('\nok\n')

    def error(self, s):
        s = re.sub(r'\s+', ' ', str(s))
        self.write('\nerror %s\n' % s)

    def _check_ok(self, onempty):
        self.outp.flush()
        rl = ''
        for rl in linereader(self.inp):
            #log('%d got line: %r\n' % (os.getpid(), rl))
            if not rl:  # empty line
                continue
            elif rl == 'ok':
                return None
            elif rl.startswith('error '):
                #log('client: error: %s\n' % rl[6:])
                return NotOk(rl[6:])
            else:
                onempty(rl)
        raise Exception('server exited unexpectedly; see errors above')

    def drain_and_check_ok(self):
        def onempty(rl):
            pass
        return self._check_ok(onempty)

    def check_ok(self):
        def onempty(rl):
            raise Exception('expected "ok", got %r' % rl)
        return self._check_ok(onempty)


def linereader(f):
    while 1:
        line = f.readline()
        if not line:
            break
        yield line[:-1]


def chunkyreader(f, count = None):
    if count != None:
        while count > 0:
            b = f.read(min(count, 65536))
            if not b:
                raise IOError('EOF with %d bytes remaining' % count)
            yield b
            count -= len(b)
    else:
        while 1:
            b = f.read(65536)
            if not b: break
            yield b


class AutoFlushIter:
    def __init__(self, it, ondone = None):
        self.it = it
        self.ondone = ondone

    def __iter__(self):
        return self
        
    def next(self):
        return self.it.next()
        
    def __del__(self):
        for i in self.it:
            pass
        if self.ondone:
            self.ondone()


def slashappend(s):
    if s and not s.endswith('/'):
        return s + '/'
    else:
        return s


def _mmap_do(f, len, flags, prot):
    if not len:
        st = os.fstat(f.fileno())
        len = st.st_size
    map = mmap.mmap(f.fileno(), len, flags, prot)
    f.close()  # map will persist beyond file close
    return map


def mmap_read(f, len = 0):
    return _mmap_do(f, len, mmap.MAP_PRIVATE, mmap.PROT_READ)


def mmap_readwrite(f, len = 0):
    return _mmap_do(f, len, mmap.MAP_SHARED, mmap.PROT_READ|mmap.PROT_WRITE)


def parse_num(s):
    g = re.match(r'([-+\d.e]+)\s*(\w*)', str(s))
    if not g:
        raise ValueError("can't parse %r as a number" % s)
    (val, unit) = g.groups()
    num = float(val)
    unit = unit.lower()
    if unit in ['t', 'tb']:
        mult = 1024*1024*1024*1024
    elif unit in ['g', 'gb']:
        mult = 1024*1024*1024
    elif unit in ['m', 'mb']:
        mult = 1024*1024
    elif unit in ['k', 'kb']:
        mult = 1024
    elif unit in ['', 'b']:
        mult = 1
    else:
        raise ValueError("invalid unit %r in number %r" % (unit, s))
    return int(num*mult)


# count the number of elements in an iterator (consumes the iterator)
def count(l):
    return reduce(lambda x,y: x+1, l)


def atoi(s):
    try:
        return int(s or '0')
    except ValueError:
        return 0


saved_errors = []
def add_error(e):
    saved_errors.append(e)
    log('%-70s\n' % e)

istty = os.isatty(2) or atoi(os.environ.get('BUP_FORCE_TTY'))
def progress(s):
    if istty:
        log(s)


def handle_ctrl_c():
    oldhook = sys.excepthook
    def newhook(exctype, value, traceback):
        if exctype == KeyboardInterrupt:
            log('Interrupted.\n')
        else:
            return oldhook(exctype, value, traceback)
    sys.excepthook = newhook


# hashlib is only available in python 2.5 or higher, but the 'sha' module
# produces a DeprecationWarning in python 2.6 or higher.  We want to support
# python 2.4 and above without any stupid warnings, so let's try using hashlib
# first, and downgrade if it fails.
try:
    import hashlib
except ImportError:
    import sha
    Sha1 = sha.sha
else:
    Sha1 = hashlib.sha1
