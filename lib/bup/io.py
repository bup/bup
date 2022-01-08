
import mmap as py_mmap

from bup.compat import pending_raise


def byte_stream(file):
    return file.buffer

def path_msg(x):
    """Return a string representation of a path."""
    # FIXME: configurability (might git-config quotePath be involved?)
    return x.decode(errors='backslashreplace')


assert not hasattr(py_mmap.mmap, '__del__')
if hasattr(py_mmap.mmap, '__enter__'):
    assert hasattr(py_mmap.mmap, '__exit__')

class mmap(py_mmap.mmap):
    '''mmap.mmap wrapper that detects and complains about any instances
    that aren't explicitly closed.

    '''

    def __init__(self, *args, **kwargs):
        self._bup_closed = True
        # Silence deprecation warnings.  mmap's current parent is
        # object, which accepts no params and as of at least 2.7
        # warns about them.
        if py_mmap.mmap.__init__ is not object.__init__:
            super(mmap, self).__init__(self, *args, **kwargs)
        self._bup_closed = False

    def close(self):
        self._bup_closed = True
        super(mmap, self).close()

    if hasattr(py_mmap.mmap, '__enter__'):
        def __enter__(self):
            super(mmap, self).__enter__()
            return self
        def __exit__(self, type, value, traceback):
            # Don't call self.close() when the parent has its own __exit__;
            # defer to it.
            self._bup_closed = True
            result = super(mmap, self).__exit__(type, value, traceback)
            return result
    else:
        def __enter__(self):
            return self
        def __exit__(self, type, value, traceback):
            with pending_raise(value, rethrow=False):
                self.close()

    def __del__(self):
        assert self._bup_closed
