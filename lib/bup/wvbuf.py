#
# The canonical source of this file is the bup project:
#   http://github.com/apenwarr/bup
#

class WvBuf:
    """A (very limited) clone of the WvStreams WvBuf buffer class.

    A WvBuf is a self-resizing buffer (a queue of bytes) designed to make
    it simple and efficient to get() data from the beginning and put()
    data to the end.

    Currently this implementation just uses string append operations and is
    kind of slow, but a better implementation could use tricks like ring
    buffers or a list of minibuffers to try to minimize memory allocation,
    like the C++ WvBuf does.
    """
    
    def __init__(self, data=''):
        self._buf = ''
        if data:
            self.put(data)

    def put(self, data):
        """Add the given python string to the buffer."""
        data = str(data)
        self._buf += data

    def peek(self, n=-1):
        """Return the first n bytes of the buffer but leave them in the
           buffer."""
        u = self.used()
        if n < 0:
            n = u
        elif n > u:
            n = u
        return self._buf[:n]

    def eat(self, n):
        """Throw away the first n bytes from the buffer."""
        self._buf = self._buf[n:]

    def get(self, n=-1):
        """Return the first n bytes of the buffer and eat() them.

        If n < 0, returns the entire buffer.
        """
        got = self.peek(n)
        self.eat(len(got))
        return got

    def get_until(self, sep):
        """Return the first bytes of the buffer, up to and including sep.

        If sep doesn't exist in the buffer, returns None.  Thus, get_until()
        might return None even if there is data remaining in the buffer.
        (This is useful if you're reading from a socket; you might later
        receive more data and put() it in the buffer, and the new data might
        contain the separator.)
        """
        p = self._buf.find(sep)
        if p >= 0:
            return self.get(p + len(sep))
        return None

    def getline(self, sep='\n'):
        """Same as get_until(sep), but sep has a default value of \n."""
        return self.get_until(sep)

    def used(self):
        """Return the number of bytes waiting in the buffer."""
        return len(self._buf)

    def __len__(self):
        """Same as used()."""
        return self.used()

    def __iter__(self):
        """Return a sequence created by repeatedly calling get(4096) on the
        buffer."""
        while self._buf:
            yield self.get(4096)

    def iterlines(self, sep='\n'):
        """Return a sequence created by repeatedly calling getline(sep).

        It is safe to call put() even while this iterator is running.
        When it reaches the last line, the iteration ends.

        If the last part of the buffer doesn't end with a \n character, it
        won't be returned by this function.
        """
        while 1:
            l = self.getline(sep)
            if not l: return
            yield l

    def __str__(self):
        """Return the contents of the entire buffer as a python string."""
        return self._buf

    def __repr__(self):
        LWM=50
        HWM=60
        if self.used() > HWM:
            return 'WvBuf(%r)' % (self.peek(LWM) + '...')
        else:
            return 'WvBuf(%r)' % self.peek()
