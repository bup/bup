#define _LARGEFILE64_SOURCE 1
#define PY_SSIZE_T_CLEAN 1
#undef NDEBUG
#include "../../config/config.h"

// According to Python, its header has to go first:
//   http://docs.python.org/2/c-api/intro.html#include-files
#include <Python.h>

#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <fcntl.h>

#ifdef HAVE_SYS_MMAN_H
#include <sys/mman.h>
#endif
#ifdef HAVE_SYS_TYPES_H
#include <sys/types.h>
#endif
#ifdef HAVE_SYS_STAT_H
#include <sys/stat.h>
#endif
#ifdef HAVE_UNISTD_H
#include <unistd.h>
#endif

#include "_hashsplit.h"
#include "bup/intprops.h"
#include "bupsplit.h"

#if defined(FS_IOC_GETFLAGS) && defined(FS_IOC_SETFLAGS)
#define BUP_HAVE_FILE_ATTRS 1
#endif

#if defined(BUP_MINCORE_BUF_TYPE) && \
    defined(POSIX_FADV_DONTNEED)
#define HASHSPLITTER_ADVISE
#ifdef BUP_HAVE_MINCORE_INCORE
#define HASHSPLITTER_MINCORE_INCORE MINCORE_INCORE
#else
// ./configure ensures that we're on Linux if MINCORE_INCORE isn't defined.
#define HASHSPLITTER_MINCORE_INCORE 1
#endif
#endif

#define min(_a, _b) (((_a) < (_b)) ? (_a) : (_b))

static size_t page_size;
static size_t fmincore_chunk_size;
static size_t advise_chunk;  // checkme
static size_t max_bits;

// FIXME: make sure the object has a good repr, including the fobj, etc.

/*
 * A HashSplitter is fed a file-like object and will determine
 * how the accumulated record stream should be split.
 */
typedef struct {
    PyObject_HEAD
    PyObject *files, *fobj;
    unsigned int bits;
    long filenum;
    size_t max_blob;
    int fd;
    PyObject *buf, *progress;
    size_t bufsz; // invariant: value must fit in a Py_ssize_t
    int eof;
    size_t start, end;
    int boundaries;
    unsigned int fanbits;
#ifdef HASHSPLITTER_ADVISE
    BUP_MINCORE_BUF_TYPE *mincore;
    size_t uncached, read;
#endif
} HashSplitter;

static void HashSplitter_unref(HashSplitter *self)
{
    Py_XDECREF(self->files);
    self->files = NULL;
    Py_XDECREF(self->fobj);
    self->fobj = NULL;
    Py_XDECREF(self->buf);
    self->buf = NULL;
    Py_XDECREF(self->progress);
    self->progress = NULL;
#ifdef HASHSPLITTER_ADVISE
    free(self->mincore);
    self->mincore = NULL;
#endif
}

static int HashSplitter_realloc(HashSplitter *self)
{
    // Allocate a new buffer and copy any unread content into it.
    PyObject *buf = PyBytes_FromStringAndSize(NULL, self->bufsz);
    PyObject *oldbuf = self->buf;

    if (!buf) {
        PyErr_Format(PyExc_MemoryError,
                     "cannot allocate %zd byte HashSplittter buffer",
                     self->bufsz);
        return -1;
    }

    self->buf = buf;

    if (oldbuf) {
        assert(self->end >= self->start);
        assert(self->end <= self->bufsz);
        memcpy(PyBytes_AS_STRING(self->buf),
               PyBytes_AS_STRING(oldbuf) + self->start,
               self->end - self->start);
        self->end -= self->start;
        self->start = 0;
        Py_DECREF(oldbuf);
    }

    return 0;
}

static PyObject *unsupported_operation_ex;

static int HashSplitter_nextfile(HashSplitter *self)
{
#ifdef HASHSPLITTER_ADVISE
    self->uncached = 0;
    self->read = 0;

    free(self->mincore);
    self->mincore = NULL;
#endif

    Py_XDECREF(self->fobj);

    /* grab the next file */
    if (!INT_ADD_OK(self->filenum, 1, &self->filenum)) {
        PyErr_SetString(PyExc_OverflowError, "hashsplitter file count overflowed");
        return -1;
    }
    self->fobj = PyIter_Next(self->files);
    if (!self->fobj) {
        if (PyErr_Occurred())
            return -1;
        return 0;
    }

    if (self->progress) {
        // CAUTION: Py_XDECREF evaluates its argument twice!
        PyObject *o = PyObject_CallFunction(self->progress, "li", self->filenum, 0);
        Py_XDECREF(o);
    }

    self->eof = 0;

    self->fd = PyObject_AsFileDescriptor(self->fobj);
    if (self->fd == -1) {
        if (PyErr_ExceptionMatches(PyExc_AttributeError)
            || PyErr_ExceptionMatches(PyExc_TypeError)
            || PyErr_ExceptionMatches(unsupported_operation_ex)) {
            PyErr_Clear();
            return 0;
        }
        return -1;
    }

#ifdef HASHSPLITTER_ADVISE
    struct stat s;
    if (fstat(self->fd, &s) < 0) {
        PyErr_Format(PyExc_IOError, "%R fstat failed: %s",
                     self->fobj, strerror(errno));
        return -1;
    }

    size_t pages;
    if (!INT_ADD_OK(s.st_size, page_size - 1, &pages)) {
        PyErr_Format(PyExc_OverflowError,
                     "%R.fileno() is too large to compute page count",
                     self->fobj);
        return -1;
    }
    pages /= page_size;

    BUP_MINCORE_BUF_TYPE *mcore = malloc(pages);
    if (!mcore) {
        PyErr_Format(PyExc_MemoryError, "cannot allocate %zd byte mincore buffer",
                     pages);
        return -1;
    }

    PyThreadState *thread_state = PyEval_SaveThread();
    off_t pos = 0;
    size_t outoffs = 0;
    while (pos < s.st_size) {
        /* mmap in chunks and fill mcore */
        size_t len = s.st_size - pos;
        if (len > fmincore_chunk_size)
            len = fmincore_chunk_size;

        int rc = 0;
        unsigned char *addr = mmap(NULL, len, PROT_NONE, MAP_PRIVATE, self->fd, pos);
        if (addr != MAP_FAILED)
            rc = mincore(addr, len, mcore + outoffs);
        if ((addr == MAP_FAILED) || (rc < 0)) {
            free(mcore);
            // FIXME: check for error and chain exceptions someday
            if (addr == MAP_FAILED)
                munmap(addr, len);
            PyEval_RestoreThread(thread_state);
            PyErr_SetFromErrno(PyExc_IOError);
            return -1;
        }
        if (munmap(addr, len)) {
            free(mcore);
            PyEval_RestoreThread(thread_state);
            PyErr_SetFromErrno(PyExc_IOError);
            return -1;
        }
        if (!INT_ADD_OK(pos, fmincore_chunk_size, &pos)) {
            free(mcore);
            PyEval_RestoreThread(thread_state);
            PyErr_Format(PyExc_OverflowError, "%R mincore position overflowed",
                         self->fobj);
            return -1;
        }
        if (!INT_ADD_OK(outoffs, fmincore_chunk_size / page_size, &outoffs)) {
            free(mcore);
            PyEval_RestoreThread(thread_state);
            PyErr_Format(PyExc_OverflowError, "%R mincore offset overflowed",
                         self->fobj);
            return -1;
        }
    }
    PyEval_RestoreThread(thread_state);
    self->mincore = mcore;
#endif
    return 0;
}

static int HashSplitter_init(HashSplitter *self, PyObject *args, PyObject *kwds)
{
    self->files = NULL;
    self->fobj = NULL;
    self->filenum = -1;
    self->buf = NULL;
    self->progress = NULL;
    self->start = 0;
    self->end = 0;
    self->boundaries = 1;
    self->fanbits = 4;
#ifdef HASHSPLITTER_ADVISE
    self->mincore = NULL;
    self->uncached = 0;
    self->read = 0;
#endif

    static char *argnames[] = {
        "files",
        "bits",
        "progress",
        "keep_boundaries",
        "fanbits",
        NULL
     };
    PyObject *files = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwds, "OI|OpI", argnames,
                                     &files, &self->bits,
                                     &self->progress, &self->boundaries,
                                     &self->fanbits))
        goto error;

    self->files = PyObject_GetIter(files);
    if (!self->files)
        goto error;

    /* simplify later checks */
    if (!self->progress || self->progress == Py_None)
        self->progress = NULL;
    else
        Py_INCREF(self->progress);

    if (self->bits < 13 || self->bits > max_bits) {
        PyErr_Format(PyExc_ValueError,
                     "invalid bits value %d (must be in [%d, %d])",
                     self->bits, 13, max_bits);
        goto error;
    }

    if (!self->fanbits) {
        PyErr_Format(PyExc_ValueError, "fanbits must be non-zero");
        goto error;
    }

    if (self->bits >= (log2(sizeof(self->max_blob)) * 8) - 2) {
        PyErr_Format(PyExc_ValueError, "bits value is too large");
    }
    self->max_blob = 1 << (self->bits + 2);

    self->bufsz = advise_chunk;

    if (HashSplitter_realloc(self))
        goto error;

    if (HashSplitter_nextfile(self))
        goto error;

    return 0;
error:
    HashSplitter_unref(self);
    return -1;
}

static PyObject *HashSplitter_iter(PyObject *self)
{
    Py_INCREF(self);
    return self;
}

static int bup_py_fadvise(int fd, off_t offset, off_t len, int advice)
{
    const int rc = posix_fadvise(fd, offset, len, advice);
    switch (rc) {
    case 0:
        return 1;
    case EBADF:
    case ESPIPE:
        PyErr_SetFromErrno(PyExc_IOError);
        return 0;
    case EINVAL:
        PyErr_SetFromErrno(PyExc_ValueError);
        return 0;
    default:
        PyErr_SetFromErrno(PyExc_OSError);
        return 0;
    }
}

#ifdef HASHSPLITTER_ADVISE
static int HashSplitter_uncache(HashSplitter *self, int last)
{
    if (!self->mincore)
        return 0;

    assert(self->uncached <= self->read);
    size_t len = self->read - self->uncached;
    if (!last) {
        len /= advise_chunk;
        len *= advise_chunk;
    }
    size_t pages = len / page_size;

    // now track where and how much to uncache
    off_t start = self->uncached; // see assumptions (off_t <= size_t)

    // Check against overflow up front
    size_t pgstart = self->uncached / page_size;
    {
        size_t tmp;
        if (!INT_ADD_OK(pgstart, pages, &tmp)) {
            PyErr_Format(PyExc_OverflowError, "%R mincore offset too big for size_t",
                         self);
            return -1;
        }
    }
    if (pages == SIZE_MAX) {
        PyErr_Format(PyExc_OverflowError, "can't handle SIZE_MAX page count for %R",
                     self);
        return -1;
    }
    size_t i;
    for (i = 0, len = 0; i < pages; i++) {
        // We check that page_size fits in an off_t elsewhere, at startup
        if (self->mincore[pgstart + i] & HASHSPLITTER_MINCORE_INCORE) {
            if (len) {
                if(!bup_py_fadvise(self->fd, start, len, POSIX_FADV_DONTNEED))
                    return -1;
            }
            start += len + page_size;
            len = 0;
        } else {
            len += page_size;
        }
    }
    if (len) {
        if(!bup_py_fadvise(self->fd, start, len, POSIX_FADV_DONTNEED))
            return -1;
    }

    if (!INT_ADD_OK(start, len, &self->uncached)) {
        PyErr_Format(PyExc_OverflowError, "%R mincore uncached size too big for size_t",
                     self);
        return -1;
    }
    return 0;
}
#endif

static int HashSplitter_read(HashSplitter *self)
{
    if (!self->fobj)
        return 0;

    assert(self->start <= self->end);
    assert(self->end <= self->bufsz);

    Py_ssize_t len = 0;
    if (self->fd != -1) {
        /* this better be the common case ... */
        Py_BEGIN_ALLOW_THREADS;
        len = read(self->fd,
                   PyBytes_AS_STRING(self->buf) + self->end,
                   self->bufsz - self->end);
        Py_END_ALLOW_THREADS;

        if (len < 0) {
            PyErr_SetFromErrno(PyExc_IOError);
            return -1;
        }

        self->end += len;

#ifdef HASHSPLITTER_ADVISE
        if (!INT_ADD_OK(self->read, len, &self->read)) {
            PyErr_Format(PyExc_OverflowError, "%R mincore read count overflowed",
                         self);
            return -1;
        }

        assert(self->uncached <= self->read);
        if (len == 0
            && self->read > self->uncached
            && self->read - self->uncached >= advise_chunk) {
            if(HashSplitter_uncache(self, len == 0))
                return -1;
        }
#endif
    } else {
        assert(self->bufsz >= self->end);
        assert(self->bufsz - self->end <= PY_SSIZE_T_MAX);
        PyObject *r = PyObject_CallMethod(self->fobj, "read", "n",
                                          self->bufsz - self->end);
        if (!r)
            return -1;

        Py_buffer buf;
        if (PyObject_GetBuffer(r, &buf, PyBUF_FULL_RO)) {
            Py_DECREF(r);
            return -1;
        }

        len = buf.len;
        assert(len >= 0);
        // see assumptions (Py_ssize_t <= size_t)
        if ((size_t) len > self->bufsz - self->end) {
            PyErr_Format(PyExc_ValueError, "read(%d) returned %zd bytes",
                         self->bufsz - self->end, len);
            PyBuffer_Release(&buf);
            Py_DECREF(r);
            return -1;
        }
        if (len)
            assert(!PyBuffer_ToContiguous(PyBytes_AS_STRING(self->buf) + self->end,
                                          &buf, len, 'C'));
        PyBuffer_Release(&buf);
        Py_DECREF(r);

        self->end += len;
    }

    if (self->progress && len) {
        PyObject *o = PyObject_CallFunction(self->progress, "ln",
                                            self->filenum, len);
        if (o == NULL)
            return -1;
        Py_DECREF(o);
    }

    return len;
}

static size_t HashSplitter_find_offs(unsigned int nbits,
                                     const unsigned char *buf,
                                     const size_t len,
                                     unsigned int *extrabits)
{
    // Return the buff offset of the next split point for a rollsum
    // watching the least significant nbits.  Set extrabits to the
    // count of contiguous one bits that are more significant than the
    // lest significant nbits and the next most significant bit (which
    // is ignored).

    assert(nbits <= 32);

    PyThreadState *thread_state = PyEval_SaveThread();

    // Compute masks for the two 16-bit rollsum components such that
    // (s1_* | s2_*) is the mask for the entire 32-bit value.  The
    // least significant nbits of the complete mask will be all ones.
    const uint16_t s2_mask = (1 << nbits) - 1;
    const uint16_t s1_mask = (nbits <= 16) ? 0 : (1 << (nbits - 16)) - 1;

    Rollsum r;
    rollsum_init(&r);

    size_t count;
    for (count = 0; count < len; count++) {
        rollsum_roll(&r, buf[count]);

        if ((r.s2 & s2_mask) == s2_mask && (r.s1 & s1_mask) == s1_mask) {
            uint32_t rsum = rollsum_digest(&r);

            rsum >>= nbits;
            /*
             * See the DESIGN document, the bit counting loop used to
             * be written in a way that shifted rsum *before* checking
             * the lowest bit, make that explicit now so the code is a
             * bit easier to understand.
             */
            rsum >>= 1;
            *extrabits = 0;
            while (rsum & 1) {
                (*extrabits)++;
                rsum >>= 1;
            }

            PyEval_RestoreThread(thread_state);
            assert(count < len);
            return count + 1;
        }
    }
    PyEval_RestoreThread(thread_state);
    return 0;
}

static PyObject *HashSplitter_iternext(HashSplitter *self)
{
    unsigned int nbits = self->bits;

    while (1) {
        assert(self->end >= self->start);
        const unsigned char *buf;

        /* read some data if possible/needed */
        if (self->end < self->bufsz && self->fobj) {
            if (self->eof && (!self->boundaries || self->start == self->end))
                HashSplitter_nextfile(self);

            int rc = HashSplitter_read(self);
            if (rc < 0)
                return NULL;
            if (rc == 0)
                self->eof = 1;
        }

        /* check first if we've completed */
        if (self->start == self->end && !self->fobj) {
            /* quick free - not really required */
            Py_DECREF(self->buf);
            self->buf = NULL;
            return NULL;
        }

        buf = (void *)PyBytes_AS_STRING(self->buf);
        const size_t maxlen = min(self->end - self->start, self->max_blob);

        unsigned int extrabits;
        size_t ofs = HashSplitter_find_offs(nbits, buf + self->start, maxlen,
                                            &extrabits);

        unsigned int level;
        if (ofs) {
            level = extrabits / self->fanbits;
        } else if (self->end - self->start >= self->max_blob) {
            ofs = self->max_blob;
            level = 0;
        } else if (self->start != self->end &&
                   self->eof && (self->boundaries || !self->fobj)) {
            ofs = self->end - self->start;
            level = 0;
        } else {
            /*
             * We've not found a split point, not been able to split
             * due to a max blob, nor reached EOF - new buffer needed.
             */
            if (HashSplitter_realloc(self))
                return NULL;
            continue;
        }
        assert(self->end - self->start >= ofs);

        /* return the found chunk as a buffer view into the total */
        PyObject *mview = PyMemoryView_FromObject(self->buf);
        PyObject *ret = PySequence_GetSlice(mview, self->start, self->start + ofs);
        Py_DECREF(mview);
        self->start += ofs;
        PyObject *result = Py_BuildValue("Ni", ret, level);
        if (result == NULL) {
            Py_DECREF(ret);
            return NULL;
        }
        return result;
    }
}

static void HashSplitter_dealloc(HashSplitter *self)
{
    HashSplitter_unref(self);
    PyObject_Del(self);
}

PyTypeObject HashSplitterType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_helpers.HashSplitter",
    .tp_doc = "Stateful hashsplitter",
    .tp_basicsize = sizeof(HashSplitter),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_new = PyType_GenericNew,
    .tp_init = (initproc)HashSplitter_init,
    .tp_iter = HashSplitter_iter,
    .tp_iternext = (iternextfunc)HashSplitter_iternext,
    .tp_dealloc = (destructor)HashSplitter_dealloc,
};

int hashsplit_init(void)
{
    // Assumptions the rest of the code can depend on.
    assert(sizeof(Py_ssize_t) <= sizeof(size_t));
    assert(sizeof(off_t) <= sizeof(size_t));
    assert(CHAR_BIT == 8);
    assert(sizeof(Py_ssize_t) <= sizeof(size_t));

    {
        PyObject *io = PyImport_ImportModule("io");
        if (!io)
            return -1;
        PyObject *ex = PyObject_GetAttrString(io, "UnsupportedOperation");
        Py_DECREF(io);
        if (!ex)
            return -1;
        unsupported_operation_ex = ex;
    }

    const long sc_page_size = sysconf(_SC_PAGESIZE);
    if (sc_page_size < 0) {
        if (errno == EINVAL)
            PyErr_SetFromErrno(PyExc_ValueError);
        else
            PyErr_SetFromErrno(PyExc_OSError);
        return -1;
    }
    if (sc_page_size == 0) {
        PyErr_Format(PyExc_Exception, "sysconf returned 0 _SC_PAGESIZE");
        return -1;
    }
    if (!INT_ADD_OK(sc_page_size, 0, &page_size)) {
        PyErr_Format(PyExc_OverflowError, "page size too large for size_t");
        return -1;
    }
    off_t tmp_off;
    if (!INT_ADD_OK(page_size, 0, &tmp_off)) {
        PyErr_Format(PyExc_OverflowError, "page size too large for off_t");
        return -1;
    }

    const size_t pref_chunk_size = 64 * 1024 * 1024;
    fmincore_chunk_size = page_size;
    if (fmincore_chunk_size < pref_chunk_size) {
        if (!INT_MULTIPLY_OK(page_size, (pref_chunk_size / page_size),
                             &fmincore_chunk_size)) {
            PyErr_Format(PyExc_OverflowError, "fmincore page size too large for size_t");
            return -1;
        }
    }

    advise_chunk = 8 * 1024 * 1024;
    /*
     * We read in advise_chunk blocks too, so max_blob cannot be
     * bigger than that, but max_blob is 4 << bits, so calculate
     * max_bits that way.
     */

    max_bits = log2(advise_chunk) - 2;

    if (page_size > advise_chunk)
        advise_chunk = page_size;

    if (advise_chunk > PY_SSIZE_T_MAX) {
        PyErr_Format(PyExc_OverflowError,
                     "hashsplitter advise buffer too large for ssize_t");
        return -1;
    }

    if (PyType_Ready(&HashSplitterType) < 0)
        return -1;

    return 0;
}
