"""Helper functions and classes for bup."""
import sys, os, pwd, subprocess, errno, socket, select, mmap, stat, re
from bup import _version


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
    """Print a log message to stderr."""
    sys.stdout.flush()
    _hard_write(sys.stderr.fileno(), s)


def mkdirp(d, mode=None):
    """Recursively create directories on path 'd'.

    Unlike os.makedirs(), it doesn't raise an exception if the last element of
    the path already exists.
    """
    try:
        if mode:
            os.makedirs(d, mode)
        else:
            os.makedirs(d)
    except OSError, e:
        if e.errno == errno.EEXIST:
            pass
        else:
            raise


def next(it):
    """Get the next item from an iterator, None if we reached the end."""
    try:
        return it.next()
    except StopIteration:
        return None


def unlink(f):
    """Delete a file at path 'f' if it currently exists.

    Unlike os.unlink(), does not throw an exception if the file didn't already
    exist.
    """
    try:
        os.unlink(f)
    except OSError, e:
        if e.errno == errno.ENOENT:
            pass  # it doesn't exist, that's what you asked for


def readpipe(argv):
    """Run a subprocess and return its output."""
    p = subprocess.Popen(argv, stdout=subprocess.PIPE)
    r = p.stdout.read()
    p.wait()
    return r


def realpath(p):
    """Get the absolute path of a file.

    Behaves like os.path.realpath, but doesn't follow a symlink for the last
    element. (ie. if 'p' itself is a symlink, this one won't follow it, but it
    will follow symlinks in p's directory)
    """
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
    """Get the user's login name."""
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
    """Get the user's full name."""
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
    """Get the FQDN of this machine."""
    global _hostname
    if not _hostname:
        _hostname = socket.getfqdn()
    return _hostname


_resource_path = None
def resource_path(subdir=''):
    global _resource_path
    if not _resource_path:
        _resource_path = os.environ.get('BUP_RESOURCE_PATH') or '.'
    return os.path.join(_resource_path, subdir)

class NotOk(Exception):
    pass

class Conn:
    """A helper class for bup's client-server protocol."""
    def __init__(self, inp, outp):
        self.inp = inp
        self.outp = outp

    def read(self, size):
        """Read 'size' bytes from input stream."""
        self.outp.flush()
        return self.inp.read(size)

    def readline(self):
        """Read from input stream until a newline is found."""
        self.outp.flush()
        return self.inp.readline()

    def write(self, data):
        """Write 'data' to output stream."""
        #log('%d writing: %d bytes\n' % (os.getpid(), len(data)))
        self.outp.write(data)

    def has_input(self):
        """Return true if input stream is readable."""
        [rl, wl, xl] = select.select([self.inp.fileno()], [], [], 0)
        if rl:
            assert(rl[0] == self.inp.fileno())
            return True
        else:
            return None

    def ok(self):
        """Indicate end of output from last sent command."""
        self.write('\nok\n')

    def error(self, s):
        """Indicate server error to the client."""
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
        """Remove all data for the current command from input stream."""
        def onempty(rl):
            pass
        return self._check_ok(onempty)

    def check_ok(self):
        """Verify that server action completed successfully."""
        def onempty(rl):
            raise Exception('expected "ok", got %r' % rl)
        return self._check_ok(onempty)


def linereader(f):
    """Generate a list of input lines from 'f' without terminating newlines."""
    while 1:
        line = f.readline()
        if not line:
            break
        yield line[:-1]


def chunkyreader(f, count = None):
    """Generate a list of chunks of data read from 'f'.

    If count is None, read until EOF is reached.

    If count is a positive integer, read 'count' bytes from 'f'. If EOF is
    reached while reading, raise IOError.
    """
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


def slashappend(s):
    """Append "/" to 's' if it doesn't aleady end in "/"."""
    if s and not s.endswith('/'):
        return s + '/'
    else:
        return s


def _mmap_do(f, sz, flags, prot):
    if not sz:
        st = os.fstat(f.fileno())
        sz = st.st_size
    map = mmap.mmap(f.fileno(), sz, flags, prot)
    f.close()  # map will persist beyond file close
    return map


def mmap_read(f, sz = 0):
    """Create a read-only memory mapped region on file 'f'.

    If sz is 0, the region will cover the entire file.
    """
    return _mmap_do(f, sz, mmap.MAP_PRIVATE, mmap.PROT_READ)


def mmap_readwrite(f, sz = 0):
    """Create a read-write memory mapped region on file 'f'.

    If sz is 0, the region will cover the entire file.
    """
    return _mmap_do(f, sz, mmap.MAP_SHARED, mmap.PROT_READ|mmap.PROT_WRITE)


def parse_num(s):
    """Parse data size information into a float number.

    Here are some examples of conversions:
        199.2k means 203981 bytes
        1GB means 1073741824 bytes
        2.1 tb means 2199023255552 bytes
    """
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


def count(l):
    """Count the number of elements in an iterator. (consumes the iterator)"""
    return reduce(lambda x,y: x+1, l)


def atoi(s):
    """Convert the string 's' to an integer. Return 0 if s is not a number."""
    try:
        return int(s or '0')
    except ValueError:
        return 0


saved_errors = []
def add_error(e):
    """Append an error message to the list of saved errors.

    Once processing is able to stop and output the errors, the saved errors are
    accessible in the module variable helpers.saved_errors.
    """
    saved_errors.append(e)
    log('%-70s\n' % e)

istty = os.isatty(2) or atoi(os.environ.get('BUP_FORCE_TTY'))
def progress(s):
    """Calls log(s) if stderr is a TTY.  Does nothing otherwise."""
    if istty:
        log(s)


def handle_ctrl_c():
    """Replace the default exception handler for KeyboardInterrupt (Ctrl-C).

    The new exception handler will make sure that bup will exit without an ugly
    stacktrace when Ctrl-C is hit.
    """
    oldhook = sys.excepthook
    def newhook(exctype, value, traceback):
        if exctype == KeyboardInterrupt:
            log('Interrupted.\n')
        else:
            return oldhook(exctype, value, traceback)
    sys.excepthook = newhook


def columnate(l, prefix):
    """Format elements of 'l' in columns with 'prefix' leading each line.

    The number of columns is determined automatically based on the string
    lengths.
    """
    if not l:
        return ""
    l = l[:]
    clen = max(len(s) for s in l)
    ncols = (78 - len(prefix)) / (clen + 2)
    if ncols <= 1:
        ncols = 1
        clen = 0
    cols = []
    while len(l) % ncols:
        l.append('')
    rows = len(l)/ncols
    for s in range(0, len(l), rows):
        cols.append(l[s:s+rows])
    out = ''
    for row in zip(*cols):
        out += prefix + ''.join(('%-*s' % (clen+2, s)) for s in row) + '\n'
    return out


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


def version_date():
    """Format bup's version date string for output."""
    return _version.DATE.split(' ')[0]

def version_commit():
    """Get the commit hash of bup's current version."""
    return _version.COMMIT

def version_tag():
    """Format bup's version tag (the official version number).

    When generated from a commit other than one pointed to with a tag, the
    returned string will be "unknown-" followed by the first seven positions of
    the commit hash.
    """
    names = _version.NAMES.strip()
    assert(names[0] == '(')
    assert(names[-1] == ')')
    names = names[1:-1]
    l = [n.strip() for n in names.split(',')]
    for n in l:
        if n.startswith('tag: bup-'):
            return n[9:]
    return 'unknown-%s' % _version.COMMIT[:7]
