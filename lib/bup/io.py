
from errno import EAGAIN
from os import fsdecode
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


_clear_line_seq = b'\x1b[0K'
_last_prog = 0
_last_progress = ''

def log(s):
    """Print a log message to stderr."""
    global _last_prog
    if _last_prog and _last_progress.endswith('\r'):
        _hard_write(sys.stderr.fileno(), _clear_line_seq)
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

def progress(s):
    """Calls log() if stderr is a TTY.  Does nothing otherwise."""
    global _last_progress
    if istty2:
        if _last_progress.endswith('\r'):
            _hard_write(sys.stderr.fileno(), _clear_line_seq)
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


def _make_enc_sh_map():
    m = [None] * 256
    for i in range(7): m[i] = br'\x%02x' % i
    m[7] = br'\a'
    m[8] = br'\b'
    m[9] = br'\t'
    m[10] = br'\n'
    m[11] = br'\v'
    m[12] = br'\f'
    m[13] = br'\r'
    for i in range(14, 27): m[i] = br'\x%02x' % i
    m[27] = br'\e' # ESC
    for i in range(28, 32): m[i] = br'\x%02x' % i
    m[39] = br"\'"
    m[92] = br'\\'
    for i in range(127, 256): m[i] = br'\x%02x' % i
    return m

_enc_sh_map = _make_enc_sh_map()

def _make_enc_shs_map():
    m = [None] * 128
    for i in range(128):
        enc = _enc_sh_map[i]
        if enc:
            m[i] = enc.decode('ascii')
    return m

_enc_shs_map = _make_enc_shs_map()


def enc_dsq(val):
    """Encode val (bytes) in POSIX $'...' (dollar-single-quote)
    format.
    https://pubs.opengroup.org/onlinepubs/9799919799/utilities/V3_chap02.html#tag_19_02_04

    """
    result = [b"$'"]
    part_start = 0
    i = 0

    def finish_part():
        nonlocal result, i, part_start
        if i != part_start:
            result.append(val[part_start:i])
        part_start = i = i + 1

    encoding = _enc_sh_map
    while i < len(val):
        b = val[i]
        enc = encoding[b]
        if enc:
            finish_part()
            result.append(enc)
        else:
            i += 1
    finish_part()
    result.append(b"'")
    return b''.join(result)

def enc_dsqs(val):
    """Encode string in POSIX $'...' (dollar-single-quote) format with
    any surrogates (from surrogate escape) \\xNN encoded as the
    original bytes. Pass through any characters whose ord() is >= 128.
    https://pubs.opengroup.org/onlinepubs/9799919799/utilities/V3_chap02.html#tag_19_02_04
    https://peps.python.org/pep-0383/

    """
    result = ["$'"]
    part_start = 0
    i = 0

    def finish_part():
        nonlocal result, i, part_start
        if i != part_start:
            result.append(val[part_start:i])
        part_start = i = i + 1

    encoding = _enc_shs_map
    while i < len(val):
        b = ord(val[i])
        if b < 128:
            enc = encoding[b]
        elif (b >= 0xdc80 and b <= 0xdcff): # surrogate escape
            enc = r'\x%02x' % (128 + (b - 0xdc80))
        else:
            enc = None
        if enc:
            finish_part()
            result.append(enc)
        else:
            i += 1
    finish_part()
    result.append("'")
    return ''.join(result)


def enc_sh(val):
    """Minimally POSIX quote val (bytes) as a single line. Use no
    quotes if possible, single quotes if val doesn't contain single
    quotes or newline, otherwise dollar-single-quote.
    https://pubs.opengroup.org/onlinepubs/9799919799/utilities/V3_chap02.html#tag_19_02

    For now, like git with core.quotePath set to false, this
    conservatively hex escapes all bytes with the high bit set,
    keeping the output compatible with any encoding that's compatible
    with ASCII, e.g. UTF-8, Latin-1, etc.

    """
    #pylint: disable=consider-using-in
    assert isinstance(val, bytes), val
    if val == b'':
        return b"''"
    need_sq = False
    need_dsq = False
    for c in val: # 32 is space
        if c < 32 or c >= 127 or c == b"'"[0]:
            need_dsq = True
            break
        # This set is everything from POSIX except ' and \n (handled above).
        if c in b'|&;<>()$`\\" \t*?[]^!#~=%{,}':
            need_sq = True
    if need_dsq:
        return enc_dsq(val)
    if need_sq:
        return b"'%s'" % val
    return val

def enc_shs(val):
    """Minimally POSIX quote val (string) as a single line. Use no
    quotes if possible, single quotes if val doesn't contain single
    quotes or newline, otherwise dollar-single-quote.
    https://pubs.opengroup.org/onlinepubs/9799919799/utilities/V3_chap02.html#tag_19_02
    https://peps.python.org/pep-0383/

    \\xNN encode any surrogates (from surrogate escape) as the
    original bytes. Pass through any characters whose ord() is >= 128.

    """
    #pylint: disable=consider-using-in
    assert isinstance(val, str), val
    if val == '':
        return "''"
    need_sq = False
    need_dsq = False
    for ch in val:
        c = ord(ch)
        if c < 32 or c == b"'"[0] or c == 127 \
           or (c >= 0xdc80 and c <= 0xdcff): # lone surrogate (PEP-0383)
            need_dsq = True
            break
        # This set is everything from POSIX except ' and \n (handled above).
        if ch in '|&;<>()$`\\" \t*?[]^!#~=%{,}':
            need_sq = True
    if need_dsq:
        return enc_dsqs(val)
    if need_sq:
        return f"'{val}'"
    return val


def path_msg(x):
    """Return a string representation of a path."""
    return enc_shs(fsdecode(x))


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
