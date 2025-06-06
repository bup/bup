"""Helper functions and classes for bup."""

from collections import namedtuple
from contextlib import ExitStack, nullcontext
from ctypes import sizeof, c_void_p
from math import floor
from os import environ
from random import SystemRandom
from subprocess import PIPE, Popen
from tempfile import mkdtemp
from shutil import rmtree
import sys, os, subprocess, errno, select, mmap, stat, re, struct
import hashlib, heapq, math, operator, time

from bup import _helpers
from bup import io
from bup.compat import argv_bytes
from bup.io import byte_stream, debug1, debug2, log, path_msg
# pylint: disable=unused-import
from bup.io import istty1, istty2, progress, qprogress, reprogress
# pylint: enable=unused-import
# This function should really be in helpers, not in bup.options.  But we
# want options.py to be standalone so people can include it in other projects.
from bup.options import _tty_width as tty_width


# EXIT_TRUE (just an alias) and EXIT_FALSE are intended for cases like
# POSIX grep or test, or bup's own "fsck --par2-ok", where the command
# is asking a question with a yes or no answer.  Eventually all
# commands should avoid exiting with 1 for errors.

EXIT_SUCCESS = 0
EXIT_TRUE = 0
EXIT_FALSE = 1
EXIT_FAILURE = 2


def dict_subset(dict, keys):
    result = {}
    for k in keys:
        if k in dict:
            result[k] = dict[k]
    return result


nullctx = nullcontext() # only need one

def nullcontext_if_not(manager):
    return manager if manager is not None else nullctx


def getgroups():
    # cf. getgroups(2) - effective group id may or may not be in the
    # list, and while on linux, for example, it normally is, in an
    # unshare, it wasn't.
    egid = os.getegid()
    gids = os.getgroups()
    if egid not in gids:
        gids.append(egid)
    return gids


class finalized:
    # pyupgrade 3.8+: add final / to make args positional only
    def __init__(self, what_or_how, how=None):
        if how is None:
            self.enter_result = None
            self.finalize = what_or_how
        else:
            self.enter_result = what_or_how
            self.finalize = how
    def __enter__(self):
        return self.enter_result
    def __exit__(self, exc_type, exc_value, traceback):
        self.finalize(self.enter_result)


def temp_dir(*args, **kwargs):
    # This is preferable to tempfile.TemporaryDirectory because the
    # latter uses @contextmanager, and so will always eventually be
    # deleted if it's handed to an ExitStack, whenever the stack is
    # gc'ed, even if you pop_all() (the new stack will also trigger
    # the deletion) because
    # https://github.com/python/cpython/issues/88458
    return finalized(mkdtemp(*args, **kwargs), lambda x: rmtree(x))


def open_in(fd, path, *args, **kwargs):
    """Open path with dir_fd set to fd via open()'s opener."""
    assert 'opener' not in kwargs
    def opener(name, mode):
        return os.open(name, mode, dir_fd=fd)
    return open(path, *args, opener=opener, **kwargs)

if hasattr(os, 'O_PATH'):
    def open_path_fd(path): return os.open(path, os.O_PATH)
else:
    def open_path_fd(path): return os.open(path, os.O_RDONLY)

def os_closed(x): return finalized(x, os.close)


# singleton used when we don't care where the object is
OBJECT_EXISTS = None

class ObjectLocation:
    __slots__ = 'pack', 'offset'
    def __init__(self, pack, offset):
        self.pack = pack
        self.offset = offset
    def __setattr__(self, k, v):
        if self is not OBJECT_EXISTS:
            return super().__setattr__(k, v)
        raise AttributeError(f'Cannot modify read-only instance attribute {k}',
                             name=k, obj=self)

OBJECT_EXISTS = ObjectLocation(None, None)

sc_arg_max = os.sysconf('SC_ARG_MAX')
if sc_arg_max == -1:  # "no definite limit" - let's choose 2M
    sc_arg_max = 2 * 1024 * 1024

def last(iterable):
    result = None
    for result in iterable:
        pass
    return result


# Note: it's been reported that Solaris (11.4's) fdatasync excludes
# some important operations (file extensions and holes) from
# fdatasync.

if not sys.platform.startswith('darwin'):
    fsync = os.fsync
    fdatasync = getattr(os, 'fdatasync', os.fsync) # currently always fdatasync
else:
    # macos doesn't guarantee to sync all the way down (see fsync(2))
    import fcntl
    def _fullsync(fd):
        try:
            # Ignore result - errors will throw, other values undocumented
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
            return True
        except IOError as e:
            # Fallback for file systems (SMB) that do not support F_FULLFSYNC
            if e.errno != errno.ENOTSUP:
                raise
            return False
    def fsync(fd): return _fullsync(fd) or os.fsync(fd)
    if getattr(os, 'fdatasync', None): # ...in case it's added someday
        def fdatasync(fd): return _fullsync(fd) or os.fdatasync(fd)
    else:
        def fdatasync(fd): return _fullsync(fd) or os.fsync(fd)


def partition(predicate, stream):
    """Returns (leading_matches_it, rest_it), where leading_matches_it
    must be completely exhausted before traversing rest_it.

    """
    stream = iter(stream)
    first_nonmatch = None
    def leading_matches():
        nonlocal first_nonmatch
        for x in stream:
            if predicate(x):
                yield x
            else:
                first_nonmatch = (x,)
                break
    def rest():
        nonlocal first_nonmatch
        if first_nonmatch:
            yield first_nonmatch[0]
            for x in stream:
                yield x
    return (leading_matches(), rest())


def lines_until_sentinel(f, sentinel, ex_type):
    # sentinel must end with \n and must contain only one \n
    while True:
        line = f.readline()
        if not (line and line.endswith(b'\n')):
            raise ex_type('Hit EOF while reading line')
        if line == sentinel:
            return
        yield line


def stat_if_exists(path):
    try:
        return os.stat(path)
    except NotADirectoryError:
        return None
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
    return None


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
    except OSError as e:
        if e.errno == errno.EEXIST:
            pass
        else:
            raise


class MergeIterItem:
    def __init__(self, entry, read_it):
        self.entry = entry
        self.read_it = read_it
    def __lt__(self, x):
        return self.entry < x.entry

def merge_iter(iters, pfreq, pfunc, pfinal, key=None):
    if key:
        samekey = lambda e, pe: getattr(e, key) == getattr(pe, key, None)
    else:
        samekey = operator.eq
    count = 0
    total = sum(len(it) for it in iters)
    iters = (iter(it) for it in iters)
    heap = ((next(it, None),it) for it in iters)
    heap = [MergeIterItem(e, it) for e, it in heap if e]

    heapq.heapify(heap)
    pe = None
    while heap:
        if not count % pfreq:
            pfunc(count, total)
        e, it = heap[0].entry, heap[0].read_it
        if not samekey(e, pe):
            pe = e
            yield e
        count += 1
        try:
            e = next(it)
        except StopIteration:
            heapq.heappop(heap) # remove current
        else:
            # shift current to new location
            heapq.heapreplace(heap, MergeIterItem(e, it))
    pfinal(count, total)


def unlink(f):
    """Delete a file at path 'f' if it currently exists.

    Unlike os.unlink(), does not throw an exception if the file didn't already
    exist.
    """
    try:
        os.unlink(f)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


_bq_simple_id_rx = re.compile(br'^[-_./a-zA-Z0-9]+$')
_sq_simple_id_rx = re.compile(r'^[-_./a-zA-Z0-9]+$')

def bquote(x):
    if x == b'':
        return b"''"
    if _bq_simple_id_rx.match(x):
        return x
    return b"'%s'" % x.replace(b"'", b"'\"'\"'")

def squote(x):
    if x == '':
        return "''"
    if _sq_simple_id_rx.match(x):
        return x
    return "'%s'" % x.replace("'", "'\"'\"'")

def quote(x):
    if isinstance(x, bytes):
        return bquote(x)
    if isinstance(x, str):
        return squote(x)
    assert False
    # some versions of pylint get confused
    return None

def shstr(cmd):
    """Return a shell quoted string for cmd if it's a sequence, else cmd.

    cmd must be a string, bytes, or a sequence of one or the other,
    and the assumption is that if cmd is a string or bytes, then it's
    already quoted (because it's what's actually being passed to
    call() and friends.  e.g. log(shstr(cmd)); call(cmd)

    """
    if isinstance(cmd, (bytes, str)):
        return cmd
    elif all(isinstance(x, bytes) for x in cmd):
        return b' '.join(map(bquote, cmd))
    elif all(isinstance(x, str) for x in cmd):
        return ' '.join(map(squote, cmd))
    raise TypeError('unsupported shstr argument: ' + repr(cmd))


exc = subprocess.check_call

def exo(cmd,
        input=None,
        stdin=None,
        stderr=None,
        shell=False,
        check=True,
        preexec_fn=None,
        close_fds=True):
    if input:
        assert stdin in (None, PIPE)
        stdin = PIPE
    p = Popen(cmd,
              stdin=stdin, stdout=PIPE, stderr=stderr,
              shell=shell,
              preexec_fn=preexec_fn,
              close_fds=close_fds)
    out, err = p.communicate(input)
    if check and p.returncode != 0:
        raise Exception('subprocess %r failed with status %d%s'
                        % (b' '.join(map(quote, cmd)), p.returncode,
                           ', stderr: %r' % err if err else ''))
    return out, err, p

def readpipe(argv, preexec_fn=None, shell=False):
    """Run a subprocess and return its output."""
    return exo(argv, preexec_fn=preexec_fn, shell=shell)[0]


def _argmax_base(command):
    base_size = 2048
    for c in command:
        base_size += len(command) + 1
    for k, v in environ.items():
        base_size += len(k) + len(v) + 2 + sizeof(c_void_p)
    return base_size


def _argmax_args_size(args):
    return sum(len(x) + 1 + sizeof(c_void_p) for x in args)


def batchpipe(command, args, preexec_fn=None, arg_max=sc_arg_max):
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


def resolve_parent(p):
    """Return the absolute path of a file without following any final symlink.

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


if sys.platform.startswith('cygwin'):
    def is_superuser():
        # https://cygwin.com/ml/cygwin/2015-02/msg00057.html
        groups = getgroups()
        return 544 in groups or 0 in groups
else:
    def is_superuser():
        return os.geteuid() == 0


def cache_key_value(get_value, key, cache):
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


_hostname = None
def hostname():
    """Get the FQDN of this machine."""
    global _hostname
    if not _hostname:
        _hostname = _helpers.gethostname()
    return _hostname


def format_filesize(size):
    unit = 1024.0
    size = float(size)
    if size < unit:
        return "%d" % (size)
    exponent = int(math.log(size) // math.log(unit))
    size_prefix = "KMGTPE"[exponent - 1]
    return "%.1f%s" % (size / math.pow(unit, exponent), size_prefix)


class NotOk(Exception):
    pass


class BaseConn:
    def __init__(self, outp):
        self._base_closed = False
        self.outp = outp

    def close(self):
        self._base_closed = True

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_value, tb): self.close()
    def __del__(self): assert self._base_closed

    def _read(self, size):
        raise NotImplementedError("Subclasses must implement _read")

    def read(self, size):
        """Read 'size' bytes from input stream."""
        self.outp.flush()
        return self._read(size)

    def _readline(self):
        raise NotImplementedError("Subclasses must implement _readline")

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
        raise NotImplementedError("Subclasses must implement has_input")

    def ok(self):
        """Indicate end of output from last sent command."""
        self.write(b'\nok\n')

    def error(self, s):
        """Indicate server error to the client."""
        s = s.encode('utf-8', errors='backslashreplace')
        s = re.sub(br'\s+', b' ', s)
        self.write(b'\nerror %s\n' % s)

    def _check_ok(self, onempty):
        self.outp.flush()
        rl = b''
        for rl in linereader(self):
            #log('%d got line: %r\n' % (os.getpid(), rl))
            if not rl:  # empty line
                continue
            elif rl == b'ok':
                return None
            elif rl.startswith(b'error '):
                #log('client: error: %s\n' % rl[6:])
                return NotOk(rl[6:].decode('utf-8', errors='surrogateescape'))
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
                    os.writev(outfd, (struct.pack('!IB', len(buf), 1), buf))
                elif fd == errr:
                    buf = os.read(errr, 1024)
                    if not buf: break
                    os.writev(outfd, (struct.pack('!IB', len(buf), 2), buf))
    finally:
        os.write(outfd, struct.pack('!IB', 0, 3))


class DemuxConn(BaseConn):
    """A helper class for bup's client-server protocol."""
    def __init__(self, infd, outp):
        BaseConn.__init__(self, outp)
        # Anything that comes through before the sync string was not
        # multiplexed and can be assumed to be debug/log before mux init.
        tail = b''
        stderr = byte_stream(sys.stderr)
        while tail != b'BUPMUX':
            # Make sure to write all pre-BUPMUX output to stderr
            b = os.read(infd, (len(tail) < 6) and (6-len(tail)) or 1)
            if not b:
                try:
                    raise IOError('demux: unexpected EOF during initialization')
                finally:
                    stderr.write(tail)
                    stderr.flush()
            tail += b
            stderr.write(tail[:-6])
            tail = tail[-6:]
        stderr.flush()
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
        ns = b''.join(checked_reader(self.infd, 5))
        n, fdw = struct.unpack('!IB', ns)
        if n > MAX_PACKET:
            # assume that something went wrong and print stuff
            ns += os.read(self.infd, 1024)
            stderr = byte_stream(sys.stderr)
            stderr.write(ns)
            stderr.flush()
            raise Exception("Connection broken")
        if fdw == 1:
            self.reader = checked_reader(self.infd, n)
        elif fdw == 2:
            for buf in checked_reader(self.infd, n):
                byte_stream(sys.stderr).write(buf)
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
                self.buf = next(self.reader)
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
                return buf.index(b'\n')+1
            except ValueError:
                return None
        return b''.join(self._read_parts(find_eol))

    def _read(self, size):
        csize = [size]
        def until_size(buf): # Closes on csize
            if len(buf) < csize[0]:
                csize[0] -= len(buf)
                return None
            else:
                return csize[0]
        return b''.join(self._read_parts(until_size))

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


class atomically_replaced_file:
    def __init__(self, path, mode='w', buffering=-1, sync=True):
        """Return a context manager supporting the atomic replacement of a file.

        The context manager yields an open file object that has been
        created in a mkdtemp-style temporary directory in the same
        directory as the path.  The temporary file will be renamed to
        the target path (atomically if the platform allows it) if
        there are no exceptions, and the temporary directory will
        always be removed.  Calling cancel() will prevent the
        replacement. When sync is true (the default), the replacement
        will be made durable in the fsync sense, otherwise, it's up to
        the caller to fsync the path parent. It's always up to the
        caller to sync the returned file itself, if desired.

        The file object will have a name attribute containing the
        file's path, and the mode and buffering arguments will be
        handled exactly as with open().  The resulting permissions
        will also match those produced by open().

        E.g.::

          with atomically_replaced_file('foo.txt', 'w') as f:
              f.write('hello jack.')
              f.flush()
              os.fsync(f.fileno())

        """
        # Anything requiring cleanup must come after _closed is set to
        # False to coordinate with __exit__ and __del__, etc.
        self._closed = True
        assert 'w' in mode
        self.path = path
        self.mode = mode
        self.buffering = buffering
        self.canceled = False
        self.tmp_path = None
        self._sync = sync
        self._tmp_dir_fd = None
        self._path_parent_fd = None
        self._path_parent, self._path_base = os.path.split(self.path)
        if not self._path_parent:
            self._path_parent = '.'
        assert self._path_base, f'{self._path_base} is a directory'
        ctx = ExitStack()
        self._cleanup = ctx
        with ctx:
            def set_closed(_): self._closed = True
            ctx.enter_context(finalized(set_closed))
            self._closed = False
            # Anything requiring cleanup must be after this and guarded by ctx
            ctx = os_closed(os.open(self._path_parent, os.O_RDONLY))
            self._path_parent_fd = self._cleanup.enter_context(ctx)
            self._cleanup = self._cleanup.pop_all()
    def __del__(self):
        assert self._closed
    def __enter__(self):
        with self._cleanup:
            tmpdir = temp_dir(dir=self._path_parent,
                              prefix=self._path_base + b'-')
            tmpdir = self._cleanup.enter_context(tmpdir)
            tmpdir_ctx = os_closed(open_path_fd(tmpdir))
            self._tmp_dir_fd = self._cleanup.enter_context(tmpdir_ctx)
            self.tmp_path = tmpdir + b'/pending'
            f = open_in(self._tmp_dir_fd, b'pending', mode=self.mode,
                        buffering=self.buffering)
            f = self._cleanup.enter_context(f)
            self._cleanup = self._cleanup.pop_all()
            return f
    def __exit__(self, exc_type, exc_value, traceback):
        with self._cleanup:
            if self.canceled or exc_type:
                return
            os.rename(b'pending', self._path_base,
                      src_dir_fd=self._tmp_dir_fd,
                      dst_dir_fd=self._path_parent_fd)
            if self._sync:
                fsync(self._path_parent_fd)
    def cancel(self):
        self.canceled = True


def slashappend(s):
    """Append "/" to 's' if it doesn't aleady end in "/"."""
    assert isinstance(s, bytes)
    if s and not s.endswith(b'/'):
        return s + b'/'
    else:
        return s


def _mmap_do(f, sz, flags, prot, close):
    with ExitStack() as contexts:
        if close:
            contexts.enter_context(f)
        if not sz:
            st = os.fstat(f.fileno())
            sz = st.st_size
        if not sz:
            # trying to open a zero-length map gives an error, but an empty
            # string has all the same behaviour of a zero-length map, ie. it has
            # no elements :)
            return b''
        return io.mmap(f.fileno(), sz, flags, prot)


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
    """Parse string or bytes as a possibly unit suffixed number.

    For example:
        199.2k means 203981 bytes
        1GB means 1073741824 bytes
        2.1 tb means 2199023255552 bytes
    """
    if isinstance(s, bytes):
        # FIXME: should this raise a ValueError for UnicodeDecodeError
        # (perhaps with the latter as the context).
        s = s.decode('ascii')
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


saved_errors = []
def add_error(e):
    """Append an error message to the list of saved errors.

    Once processing is able to stop and output the errors, the saved errors are
    accessible in the module variable helpers.saved_errors.
    """
    saved_errors.append(e)
    log('%-70s\n' % e)

def note_error(m):
    # FIXME: rework console output, logging, and api...
    saved_errors.append(m)
    log(m)

def clear_errors():
    global saved_errors
    saved_errors = []


def die_if_errors(msg=None, status=EXIT_FAILURE):
    global saved_errors
    if saved_errors:
        if not msg:
            msg = 'warning: %d errors encountered\n' % len(saved_errors)
        log(msg)
        sys.exit(status)


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
            oldhook(exctype, value, traceback)
    sys.excepthook = newhook


def columnate(l, prefix):
    """Format elements of 'l' in columns with 'prefix' leading each line.

    The number of columns is determined automatically based on the string
    lengths.
    """
    binary = isinstance(prefix, bytes)
    nothing = b'' if binary else ''
    nl = b'\n' if binary else '\n'
    if not l:
        return nothing
    l = l[:]
    clen = max(len(s) for s in l)
    ncols = (tty_width() - len(prefix)) // (clen + 2)
    if ncols <= 1:
        ncols = 1
        clen = 0
    cols = []
    while len(l) % ncols:
        l.append(nothing)
    rows = len(l) // ncols
    for s in range(0, len(l), rows):
        cols.append(l[s:s+rows])
    out = []
    fmt = b'%-*s' if binary else '%-*s'
    for row in zip(*cols):
        out.append(prefix + nothing.join((fmt % (clen+2, s)) for s in row) + nl)
    return nothing.join(out)


def parse_date_or_fatal(str, fatal):
    """Parses the given date or calls Option.fatal().
    For now we expect a string that contains a float."""
    try:
        date = float(str)
    except ValueError as e:
        raise fatal('invalid date format (should be a float): %r' % e)
    else:
        return date


def parse_excludes(options, fatal):
    """Traverse the options and extract all excludes, or call Option.fatal()."""
    excluded_paths = []

    for flag in options:
        (option, parameter) = flag
        if option == '--exclude':
            excluded_paths.append(resolve_parent(argv_bytes(parameter)))
        elif option == '--exclude-from':
            try:
                f = open(resolve_parent(argv_bytes(parameter)), 'rb')
            except IOError as e:
                raise fatal("couldn't read %r" % parameter)
            for exclude_path in f.readlines():
                # FIXME: perhaps this should be rstrip('\n')
                exclude_path = resolve_parent(exclude_path.strip())
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
                excluded_patterns.append(re.compile(argv_bytes(parameter)))
            except re.error as ex:
                fatal('invalid --exclude-rx pattern (%r): %s' % (parameter, ex))
        elif option == '--exclude-rx-from':
            try:
                f = open(resolve_parent(parameter), 'rb')
            except IOError as e:
                fatal("couldn't read %r" % parameter)
            for pattern in f.readlines():
                spattern = pattern.rstrip(b'\n')
                if not spattern:
                    continue
                try:
                    excluded_patterns.append(re.compile(spattern))
                except re.error as ex:
                    fatal('invalid --exclude-rx pattern (%r): %s' % (spattern, ex))
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
    if not path.startswith(b'/'):
        raise Exception('path must start with "/": %s' % path_msg(path))
    # Since we assume path startswith('/'), we can skip the first element.
    result = [(b'', b'/')]
    norm_path = os.path.abspath(path)
    if norm_path == b'/':
        return result
    full_path = b''
    for p in norm_path.split(b'/')[1:]:
        full_path += b'/' + p
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
        if normalized_bp == b'/':
            continue
        if normalized_path.startswith(normalized_bp):
            prefix = normalized_path[:len(normalized_bp)]
            result = []
            for p in normalized_path[len(normalized_bp):].split(b'/'):
                if p: # not root
                    prefix += b'/'
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
            grafted_path = re.sub(br'^' + escaped_prefix, new_prefix, clean_path)
            # Handle /foo=/ (at least) -- which produces //whatever.
            grafted_path = b'/' + grafted_path.lstrip(b'/')
            clean_path_components = path_components(clean_path)
            # Count the components that were stripped.
            strip_count = 0 if old_prefix == b'/' else old_prefix.count(b'/')
            new_prefix_parts = new_prefix.split(b'/')
            result_prefix = grafted_path.split(b'/')[:new_prefix.count(b'/')]
            result = [(p, None) for p in result_prefix] \
                + clean_path_components[strip_count:]
            # Now set the graft point name to match the end of new_prefix.
            graft_point = len(result_prefix)
            result[graft_point] = \
                (new_prefix_parts[-1], clean_path_components[strip_count][1])
            if new_prefix == b'/': # --graft ...=/ is a special case.
                return result[1:]
            return result
    return path_components(clean_path)


Sha1 = hashlib.sha1


_localtime = getattr(_helpers, 'localtime', None)

if _localtime:
    bup_time = namedtuple('bup_time', ['tm_year', 'tm_mon', 'tm_mday',
                                       'tm_hour', 'tm_min', 'tm_sec',
                                       'tm_wday', 'tm_yday',
                                       'tm_isdst', 'tm_gmtoff', 'tm_zone'])

# Define a localtime() that returns bup_time when possible.  Note:
# this means that any helpers.localtime() results may need to be
# passed through to_py_time() before being passed to python's time
# module, which doesn't appear willing to ignore the extra items.
if _localtime:
    def localtime(time):
        return bup_time(*_helpers.localtime(int(floor(time))))
    def utc_offset_str(t):
        """Return the local offset from UTC as "+hhmm" or "-hhmm" for time t.
        If the current UTC offset does not represent an integer number
        of minutes, the fractional component will be truncated."""
        off = localtime(t).tm_gmtoff
        # Note: // doesn't truncate like C for negative values, it rounds down.
        offmin = abs(off) // 60
        m = offmin % 60
        h = (offmin - m) // 60
        return b'%+03d%02d' % (-h if off < 0 else h, m)
    def to_py_time(x):
        if isinstance(x, time.struct_time):
            return x
        return time.struct_time(x[:9])
else:
    localtime = time.localtime
    def utc_offset_str(t):
        return time.strftime('%z', localtime(t)).encode('ascii')
    def to_py_time(x):
        return x


_some_invalid_save_parts_rx = re.compile(br'[\[ ~^:?*\\]|\.\.|//|@{')

def valid_save_name(name):
    # Enforce a superset of the restrictions in git-check-ref-format(1)
    if name == b'@' \
       or name.startswith(b'/') or name.endswith(b'/') \
       or name.endswith(b'.'):
        return False
    if _some_invalid_save_parts_rx.search(name):
        return False
    for c in name:
        if c < 0x20 or c == 0x7f:
            return False
    for part in name.split(b'/'):
        if part.startswith(b'.') or part.endswith(b'.lock'):
            return False
    return True


_period_rx = re.compile(br'^([0-9]+)(s|min|h|d|w|m|y)$')

def period_as_secs(s):
    if s == b'forever':
        return float('inf')
    match = _period_rx.match(s)
    if not match:
        return None
    mag = int(match.group(1))
    scale = match.group(2)
    return mag * {b's': 1,
                  b'min': 60,
                  b'h': 60 * 60,
                  b'd': 60 * 60 * 24,
                  b'w': 60 * 60 * 24 * 7,
                  b'm': 60 * 60 * 24 * 31,
                  b'y': 60 * 60 * 24 * 366}[scale]


def make_repo_id(n=31):
    rnd = SystemRandom()
    chars = b'abcdefghijklmnopqrstuvwxyz0123456789'
    return bytes(rnd.choice(chars) for x in range(n))
