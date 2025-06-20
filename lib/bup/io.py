
from errno import EAGAIN
import mmap as py_mmap
import os, select, sys, time


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
        except OSError as e:
            if e.errno != EAGAIN:
                raise
        assert(sz >= 0)
        buf = buf[sz:]


_last_prog = 0
def log(s):
    """Print a log message to stderr."""
    global _last_prog
    sys.stdout.flush()
    _hard_write(sys.stderr.fileno(), s if isinstance(s, bytes) else s.encode())
    _last_prog = 0


buglvl = int(os.environ.get('BUP_DEBUG', 0))

def debug1(s):
    if buglvl >= 1:
        log(s)

def debug2(s):
    if buglvl >= 2:
        log(s)


istty1 = os.isatty(1) or (int(os.environ.get('BUP_FORCE_TTY', 0)) & 1)
istty2 = os.isatty(2) or (int(os.environ.get('BUP_FORCE_TTY', 0)) & 2)
_last_progress = ''
def progress(s):
    """Calls log() if stderr is a TTY.  Does nothing otherwise."""
    global _last_progress
    if istty2:
        if _last_progress.endswith('\r'):
            log('\x1b[0K')
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


def byte_stream(file):
    return file.buffer


def path_msg(x):
    """Return a string representation of a path."""
    # FIXME: configurability (might git-config quotePath be involved?)
    return x.decode(errors='backslashreplace')


assert not hasattr(py_mmap.mmap, '__del__')

class mmap(py_mmap.mmap):
    '''mmap.mmap wrapper that detects and complains about any instances
    that aren't explicitly closed.

    '''
    def __new__(cls, *args, **kwargs):
        result = super().__new__(cls, *args, **kwargs)
        result._bup_closed = True  # supports __del__
        return result

    def __init__(self, *args, **kwargs):
        # Silence deprecation warnings.  mmap's current parent is
        # object, which accepts no params and as of at least 2.7
        # warns about them.
        if py_mmap.mmap.__init__ is not object.__init__:
            super().__init__(self, *args, **kwargs)
        self._bup_closed = False

    def close(self):
        self._bup_closed = True
        super().close()

    def __enter__(self):
        super().__enter__()
        return self
    def __exit__(self, type, value, traceback):
        # Don't call self.close() when the parent has its own __exit__;
        # defer to it.
        self._bup_closed = True
        result = super().__exit__(type, value, traceback)
        return result

    def __del__(self):
        assert self._bup_closed
