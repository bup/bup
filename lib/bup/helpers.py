"""Helper functions and classes for bup."""

from ctypes import sizeof, c_void_p
from os import environ
from contextlib import contextmanager
import sys, os, pwd, subprocess, errno, socket, select, mmap, stat, re, struct
import hashlib, heapq, operator, time, grp, tempfile

from bup import _helpers
import bup._helpers as _helpers
import math

# This function should really be in helpers, not in bup.options.  But we
# want options.py to be standalone so people can include it in other projects.
from bup.options import _tty_width
tty_width = _tty_width


def atoi(s):
    """Convert the string 's' to an integer. Return 0 if s is not a number."""
    try:
        return int(s or '0')
    except ValueError:
        return 0


def atof(s):
    """Convert the string 's' to a float. Return 0 if s is not a number."""
    try:
        return float(s or '0')
    except ValueError:
        return 0


buglvl = atoi(os.environ.get('BUP_DEBUG', 0))


# If the platform doesn't have fdatasync (OS X), fall back to fsync.
try:
    fdatasync = os.fdatasync
except AttributeError:
    fdatasync = os.fsync


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


_last_prog = 0
def log(s):
    """Print a log message to stderr."""
    global _last_prog
    sys.stdout.flush()
    _hard_write(sys.stderr.fileno(), s)
    _last_prog = 0


def debug1(s):
    if buglvl >= 1:
        log(s)


def debug2(s):
    if buglvl >= 2:
        log(s)


istty1 = os.isatty(1) or (atoi(os.environ.get('BUP_FORCE_TTY')) & 1)
istty2 = os.isatty(2) or (atoi(os.environ.get('BUP_FORCE_TTY')) & 2)
_last_progress = ''
def progress(s):
    """Calls log() if stderr is a TTY.  Does nothing otherwise."""
    global _last_progress
    if istty2:
        log(s)
        _last_progress = s


def qprogress(s):
    """Calls progress() only if we haven't printed progress in a while.
    
    This avoids overloading the stderr buffer with excess junk.
    """
    global _last_prog
    now = time.time()
    if now - _last_prog > 0.1:
        progress(s)
        _last_prog = now


def reprogress():
    """Calls progress() to redisplay the most recent progress message.

    Useful after you've printed some other message that wipes out the
    progress line.
    """
    if _last_progress and _last_progress.endswith('\r'):
        progress(_last_progress)


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


_unspecified_next_default = object()

def _fallback_next(it, default=_unspecified_next_default):
    """Retrieve the next item from the iterator by calling its
    next() method. If default is given, it is returned if the
    iterator is exhausted, otherwise StopIteration is raised."""

    if default is _unspecified_next_default:
        return it.next()
    else:
        try:
            return it.next()
        except StopIteration:
            return default

if sys.version_info < (2, 6):
    next =  _fallback_next


def merge_iter(iters, pfreq, pfunc, pfinal, key=None):
    if key:
        samekey = lambda e, pe: getattr(e, key) == getattr(pe, key, None)
    else:
        samekey = operator.eq
    count = 0
    total = sum(len(it) for it in iters)
    iters = (iter(it) for it in iters)
    heap = ((next(it, None),it) for it in iters)
    heap = [(e,it) for e,it in heap if e]

    heapq.heapify(heap)
    pe = None
    while heap:
        if not count % pfreq:
            pfunc(count, total)
        e, it = heap[0]
        if not samekey(e, pe):
            pe = e
            yield e
        count += 1
        try:
            e = it.next() # Don't use next() function, it's too expensive
        except StopIteration:
            heapq.heappop(heap) # remove current
        else:
            heapq.heapreplace(heap, (e, it)) # shift current to new location
    pfinal(count, total)


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


def readpipe(argv, preexec_fn=None):
    """Run a subprocess and return its output."""
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, preexec_fn=preexec_fn)
    out, err = p.communicate()
    if p.returncode != 0:
        raise Exception('subprocess %r failed with status %d'
                        % (' '.join(argv), p.returncode))
    return out


def _argmax_base(command):
    base_size = 2048
    for c in command:
        base_size += len(command) + 1
    for k, v in environ.iteritems():
        base_size += len(k) + len(v) + 2 + sizeof(c_void_p)
    return base_size


def _argmax_args_size(args):
    return sum(len(x) + 1 + sizeof(c_void_p) for x in args)


def batchpipe(command, args, preexec_fn=None, arg_max=_helpers.SC_ARG_MAX):
    """If args is not empty, yield the output produced by calling the
command list with args as a sequence of strings (It may be necessary
to return multiple strings in order to respect ARG_MAX)."""
    # The optional arg_max arg is a workaround for an issue with the
    # current wvtest behavior.
    base_size = _argmax_base(command)
    while args:
        room = arg_max - base_size
        i = 0
        while i < len(args):
            next_size = _argmax_args_size(args[i:i+1])
            if room - next_size < 0:
                break
            room -= next_size
            i += 1
        sub_args = args[:i]
        args = args[i:]
        assert(len(sub_args))
        yield readpipe(command + sub_args, preexec_fn=preexec_fn)


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


def detect_fakeroot():
    "Return True if we appear to be running under fakeroot."
    return os.getenv("FAKEROOTKEY") != None


def is_superuser():
    if sys.platform.startswith('cygwin'):
        import ctypes
        return ctypes.cdll.shell32.IsUserAnAdmin()
    else:
        return os.geteuid() == 0


def _cache_key_value(get_value, key, cache):
    """Return (value, was_cached).  If there is a value in the cache
    for key, use that, otherwise, call get_value(key) which should
    throw a KeyError if there is no value -- in which case the cached
    and returned value will be None.
    """
    try: # Do we already have it (or know there wasn't one)?
        value = cache[key]
        return value, True
    except KeyError:
        pass
    value = None
    try:
        cache[key] = value = get_value(key)
    except KeyError:
        cache[key] = None
    return value, False


_uid_to_pwd_cache = {}
_name_to_pwd_cache = {}

def pwd_from_uid(uid):
    """Return password database entry for uid (may be a cached value).
    Return None if no entry is found.
    """
    global _uid_to_pwd_cache, _name_to_pwd_cache
    entry, cached = _cache_key_value(pwd.getpwuid, uid, _uid_to_pwd_cache)
    if entry and not cached:
        _name_to_pwd_cache[entry.pw_name] = entry
    return entry


def pwd_from_name(name):
    """Return password database entry for name (may be a cached value).
    Return None if no entry is found.
    """
    global _uid_to_pwd_cache, _name_to_pwd_cache
    entry, cached = _cache_key_value(pwd.getpwnam, name, _name_to_pwd_cache)
    if entry and not cached:
        _uid_to_pwd_cache[entry.pw_uid] = entry
    return entry


_gid_to_grp_cache = {}
_name_to_grp_cache = {}

def grp_from_gid(gid):
    """Return password database entry for gid (may be a cached value).
    Return None if no entry is found.
    """
    global _gid_to_grp_cache, _name_to_grp_cache
    entry, cached = _cache_key_value(grp.getgrgid, gid, _gid_to_grp_cache)
    if entry and not cached:
        _name_to_grp_cache[entry.gr_name] = entry
    return entry


def grp_from_name(name):
    """Return password database entry for name (may be a cached value).
    Return None if no entry is found.
    """
    global _gid_to_grp_cache, _name_to_grp_cache
    entry, cached = _cache_key_value(grp.getgrnam, name, _name_to_grp_cache)
    if entry and not cached:
        _gid_to_grp_cache[entry.gr_gid] = entry
    return entry


_username = None
def username():
    """Get the user's login name."""
    global _username
    if not _username:
        uid = os.getuid()
        _username = pwd_from_uid(uid)[0] or 'user%d' % uid
    return _username


_userfullname = None
def userfullname():
    """Get the user's full name."""
    global _userfullname
    if not _userfullname:
        uid = os.getuid()
        entry = pwd_from_uid(uid)
        if entry:
            _userfullname = entry[4].split(',')[0] or entry[0]
        if not _userfullname:
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

def format_filesize(size):
    unit = 1024.0
    size = float(size)
    if size < unit:
        return "%d" % (size)
    exponent = int(math.log(size) / math.log(unit))
    size_prefix = "KMGTPE"[exponent - 1]
    return "%.1f%s" % (size / math.pow(unit, exponent), size_prefix)


class NotOk(Exception):
    pass


class BaseConn:
    def __init__(self, outp):
        self.outp = outp

    def close(self):
        while self._read(65536): pass

    def read(self, size):
        """Read 'size' bytes from input stream."""
        self.outp.flush()
        return self._read(size)

    def readline(self):
        """Read from input stream until a newline is found."""
        self.outp.flush()
        return self._readline()

    def write(self, data):
        """Write 'data' to output stream."""
        #log('%d writing: %d bytes\n' % (os.getpid(), len(data)))
        self.outp.write(data)

    def has_input(self):
        """Return true if input stream is readable."""
        raise NotImplemented("Subclasses must implement has_input")

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
        for rl in linereader(self):
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


class Conn(BaseConn):
    def __init__(self, inp, outp):
        BaseConn.__init__(self, outp)
        self.inp = inp

    def _read(self, size):
        return self.inp.read(size)

    def _readline(self):
        return self.inp.readline()

    def has_input(self):
        [rl, wl, xl] = select.select([self.inp.fileno()], [], [], 0)
        if rl:
            assert(rl[0] == self.inp.fileno())
            return True
        else:
            return None


def checked_reader(fd, n):
    while n > 0:
        rl, _, _ = select.select([fd], [], [])
        assert(rl[0] == fd)
        buf = os.read(fd, n)
        if not buf: raise Exception("Unexpected EOF reading %d more bytes" % n)
        yield buf
        n -= len(buf)


MAX_PACKET = 128 * 1024
def mux(p, outfd, outr, errr):
    try:
        fds = [outr, errr]
        while p.poll() is None:
            rl, _, _ = select.select(fds, [], [])
            for fd in rl:
                if fd == outr:
                    buf = os.read(outr, MAX_PACKET)
                    if not buf: break
                    os.write(outfd, struct.pack('!IB', len(buf), 1) + buf)
                elif fd == errr:
                    buf = os.read(errr, 1024)
                    if not buf: break
                    os.write(outfd, struct.pack('!IB', len(buf), 2) + buf)
    finally:
        os.write(outfd, struct.pack('!IB', 0, 3))


class DemuxConn(BaseConn):
    """A helper class for bup's client-server protocol."""
    def __init__(self, infd, outp):
        BaseConn.__init__(self, outp)
        # Anything that comes through before the sync string was not
        # multiplexed and can be assumed to be debug/log before mux init.
        tail = ''
        while tail != 'BUPMUX':
            b = os.read(infd, (len(tail) < 6) and (6-len(tail)) or 1)
            if not b:
                raise IOError('demux: unexpected EOF during initialization')
            tail += b
            sys.stderr.write(tail[:-6])  # pre-mux log messages
            tail = tail[-6:]
        self.infd = infd
        self.reader = None
        self.buf = None
        self.closed = False

    def write(self, data):
        self._load_buf(0)
        BaseConn.write(self, data)

    def _next_packet(self, timeout):
        if self.closed: return False
        rl, wl, xl = select.select([self.infd], [], [], timeout)
        if not rl: return False
        assert(rl[0] == self.infd)
        ns = ''.join(checked_reader(self.infd, 5))
        n, fdw = struct.unpack('!IB', ns)
        assert(n <= MAX_PACKET)
        if fdw == 1:
            self.reader = checked_reader(self.infd, n)
        elif fdw == 2:
            for buf in checked_reader(self.infd, n):
                sys.stderr.write(buf)
        elif fdw == 3:
            self.closed = True
            debug2("DemuxConn: marked closed\n")
        return True

    def _load_buf(self, timeout):
        if self.buf is not None:
            return True
        while not self.closed:
            while not self.reader:
                if not self._next_packet(timeout):
                    return False
            try:
                self.buf = self.reader.next()
                return True
            except StopIteration:
                self.reader = None
        return False

    def _read_parts(self, ix_fn):
        while self._load_buf(None):
            assert(self.buf is not None)
            i = ix_fn(self.buf)
            if i is None or i == len(self.buf):
                yv = self.buf
                self.buf = None
            else:
                yv = self.buf[:i]
                self.buf = self.buf[i:]
            yield yv
            if i is not None:
                break

    def _readline(self):
        def find_eol(buf):
            try:
                return buf.index('\n')+1
            except ValueError:
                return None
        return ''.join(self._read_parts(find_eol))

    def _read(self, size):
        csize = [size]
        def until_size(buf): # Closes on csize
            if len(buf) < csize[0]:
                csize[0] -= len(buf)
                return None
            else:
                return csize[0]
        return ''.join(self._read_parts(until_size))

    def has_input(self):
        return self._load_buf(0)


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


@contextmanager
def atomically_replaced_file(name, mode='w', buffering=-1):
    """Yield a file that will be atomically renamed name when leaving the block.

    This contextmanager yields an open file object that is backed by a
    temporary file which will be renamed (atomically) to the target
    name if everything succeeds.

    The mode and buffering arguments are handled exactly as with open,
    and the yielded file will have have very restrictive permissions,
    as per mkstemp.

    E.g.::

        with atomically_replaced_file('foo.txt', 'w') as f:
            f.write('hello jack.')

    """

    (ffd, tempname) = tempfile.mkstemp(dir=os.path.dirname(name),
                                       text=('b' not in mode))
    try:
        try:
            f = os.fdopen(ffd, mode, buffering)
        except:
            os.close(ffd)
            raise
        try:
            yield f
        finally:
            f.close()
        os.rename(tempname, name)
    finally:
        unlink(tempname)  # nonexistant file is ignored


def slashappend(s):
    """Append "/" to 's' if it doesn't aleady end in "/"."""
    if s and not s.endswith('/'):
        return s + '/'
    else:
        return s


def _mmap_do(f, sz, flags, prot, close):
    if not sz:
        st = os.fstat(f.fileno())
        sz = st.st_size
    if not sz:
        # trying to open a zero-length map gives an error, but an empty
        # string has all the same behaviour of a zero-length map, ie. it has
        # no elements :)
        return ''
    map = mmap.mmap(f.fileno(), sz, flags, prot)
    if close:
        f.close()  # map will persist beyond file close
    return map


def mmap_read(f, sz = 0, close=True):
    """Create a read-only memory mapped region on file 'f'.
    If sz is 0, the region will cover the entire file.
    """
    return _mmap_do(f, sz, mmap.MAP_PRIVATE, mmap.PROT_READ, close)


def mmap_readwrite(f, sz = 0, close=True):
    """Create a read-write memory mapped region on file 'f'.
    If sz is 0, the region will cover the entire file.
    """
    return _mmap_do(f, sz, mmap.MAP_SHARED, mmap.PROT_READ|mmap.PROT_WRITE,
                    close)


def mmap_readwrite_private(f, sz = 0, close=True):
    """Create a read-write memory mapped region on file 'f'.
    If sz is 0, the region will cover the entire file.
    The map is private, which means the changes are never flushed back to the
    file.
    """
    return _mmap_do(f, sz, mmap.MAP_PRIVATE, mmap.PROT_READ|mmap.PROT_WRITE,
                    close)


def parse_timestamp(epoch_str):
    """Return the number of nanoseconds since the epoch that are described
by epoch_str (100ms, 100ns, ...); when epoch_str cannot be parsed,
throw a ValueError that may contain additional information."""
    ns_per = {'s' :  1000000000,
              'ms' : 1000000,
              'us' : 1000,
              'ns' : 1}
    match = re.match(r'^((?:[-+]?[0-9]+)?)(s|ms|us|ns)$', epoch_str)
    if not match:
        if re.match(r'^([-+]?[0-9]+)$', epoch_str):
            raise ValueError('must include units, i.e. 100ns, 100ms, ...')
        raise ValueError()
    (n, units) = match.group(1, 2)
    if not n:
        n = 1
    n = int(n)
    return n * ns_per[units]


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


saved_errors = []
def add_error(e):
    """Append an error message to the list of saved errors.

    Once processing is able to stop and output the errors, the saved errors are
    accessible in the module variable helpers.saved_errors.
    """
    saved_errors.append(e)
    log('%-70s\n' % e)


def clear_errors():
    global saved_errors
    saved_errors = []


def handle_ctrl_c():
    """Replace the default exception handler for KeyboardInterrupt (Ctrl-C).

    The new exception handler will make sure that bup will exit without an ugly
    stacktrace when Ctrl-C is hit.
    """
    oldhook = sys.excepthook
    def newhook(exctype, value, traceback):
        if exctype == KeyboardInterrupt:
            log('\nInterrupted.\n')
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
    ncols = (tty_width() - len(prefix)) / (clen + 2)
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


def parse_date_or_fatal(str, fatal):
    """Parses the given date or calls Option.fatal().
    For now we expect a string that contains a float."""
    try:
        date = atof(str)
    except ValueError, e:
        raise fatal('invalid date format (should be a float): %r' % e)
    else:
        return date


def parse_excludes(options, fatal):
    """Traverse the options and extract all excludes, or call Option.fatal()."""
    excluded_paths = []

    for flag in options:
        (option, parameter) = flag
        if option == '--exclude':
            excluded_paths.append(realpath(parameter))
        elif option == '--exclude-from':
            try:
                f = open(realpath(parameter))
            except IOError, e:
                raise fatal("couldn't read %s" % parameter)
            for exclude_path in f.readlines():
                # FIXME: perhaps this should be rstrip('\n')
                exclude_path = realpath(exclude_path.strip())
                if exclude_path:
                    excluded_paths.append(exclude_path)
    return sorted(frozenset(excluded_paths))


def parse_rx_excludes(options, fatal):
    """Traverse the options and extract all rx excludes, or call
    Option.fatal()."""
    excluded_patterns = []

    for flag in options:
        (option, parameter) = flag
        if option == '--exclude-rx':
            try:
                excluded_patterns.append(re.compile(parameter))
            except re.error, ex:
                fatal('invalid --exclude-rx pattern (%s): %s' % (parameter, ex))
        elif option == '--exclude-rx-from':
            try:
                f = open(realpath(parameter))
            except IOError, e:
                raise fatal("couldn't read %s" % parameter)
            for pattern in f.readlines():
                spattern = pattern.rstrip('\n')
                if not spattern:
                    continue
                try:
                    excluded_patterns.append(re.compile(spattern))
                except re.error, ex:
                    fatal('invalid --exclude-rx pattern (%s): %s' % (spattern, ex))
    return excluded_patterns


def should_rx_exclude_path(path, exclude_rxs):
    """Return True if path matches a regular expression in exclude_rxs."""
    for rx in exclude_rxs:
        if rx.search(path):
            debug1('Skipping %r: excluded by rx pattern %r.\n'
                   % (path, rx.pattern))
            return True
    return False


# FIXME: Carefully consider the use of functions (os.path.*, etc.)
# that resolve against the current filesystem in the strip/graft
# functions for example, but elsewhere as well.  I suspect bup's not
# always being careful about that.  For some cases, the contents of
# the current filesystem should be irrelevant, and consulting it might
# produce the wrong result, perhaps via unintended symlink resolution,
# for example.

def path_components(path):
    """Break path into a list of pairs of the form (name,
    full_path_to_name).  Path must start with '/'.
    Example:
      '/home/foo' -> [('', '/'), ('home', '/home'), ('foo', '/home/foo')]"""
    if not path.startswith('/'):
        raise Exception, 'path must start with "/": %s' % path
    # Since we assume path startswith('/'), we can skip the first element.
    result = [('', '/')]
    norm_path = os.path.abspath(path)
    if norm_path == '/':
        return result
    full_path = ''
    for p in norm_path.split('/')[1:]:
        full_path += '/' + p
        result.append((p, full_path))
    return result


def stripped_path_components(path, strip_prefixes):
    """Strip any prefix in strip_prefixes from path and return a list
    of path components where each component is (name,
    none_or_full_fs_path_to_name).  Assume path startswith('/').
    See thelpers.py for examples."""
    normalized_path = os.path.abspath(path)
    sorted_strip_prefixes = sorted(strip_prefixes, key=len, reverse=True)
    for bp in sorted_strip_prefixes:
        normalized_bp = os.path.abspath(bp)
        if normalized_path.startswith(normalized_bp):
            prefix = normalized_path[:len(normalized_bp)]
            result = []
            for p in normalized_path[len(normalized_bp):].split('/'):
                if p: # not root
                    prefix += '/'
                prefix += p
                result.append((p, prefix))
            return result
    # Nothing to strip.
    return path_components(path)


def grafted_path_components(graft_points, path):
    # Create a result that consists of some number of faked graft
    # directories before the graft point, followed by all of the real
    # directories from path that are after the graft point.  Arrange
    # for the directory at the graft point in the result to correspond
    # to the "orig" directory in --graft orig=new.  See t/thelpers.py
    # for some examples.

    # Note that given --graft orig=new, orig and new have *nothing* to
    # do with each other, even if some of their component names
    # match. i.e. --graft /foo/bar/baz=/foo/bar/bax is semantically
    # equivalent to --graft /foo/bar/baz=/x/y/z, or even
    # /foo/bar/baz=/x.

    # FIXME: This can't be the best solution...
    clean_path = os.path.abspath(path)
    for graft_point in graft_points:
        old_prefix, new_prefix = graft_point
        # Expand prefixes iff not absolute paths.
        old_prefix = os.path.normpath(old_prefix)
        new_prefix = os.path.normpath(new_prefix)
        if clean_path.startswith(old_prefix):
            escaped_prefix = re.escape(old_prefix)
            grafted_path = re.sub(r'^' + escaped_prefix, new_prefix, clean_path)
            # Handle /foo=/ (at least) -- which produces //whatever.
            grafted_path = '/' + grafted_path.lstrip('/')
            clean_path_components = path_components(clean_path)
            # Count the components that were stripped.
            strip_count = 0 if old_prefix == '/' else old_prefix.count('/')
            new_prefix_parts = new_prefix.split('/')
            result_prefix = grafted_path.split('/')[:new_prefix.count('/')]
            result = [(p, None) for p in result_prefix] \
                + clean_path_components[strip_count:]
            # Now set the graft point name to match the end of new_prefix.
            graft_point = len(result_prefix)
            result[graft_point] = \
                (new_prefix_parts[-1], clean_path_components[strip_count][1])
            if new_prefix == '/': # --graft ...=/ is a special case.
                return result[1:]
            return result
    return path_components(clean_path)

Sha1 = hashlib.sha1
