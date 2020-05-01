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

#include "bupsplit.h"
#include "_hashsplit.h"

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

static long page_size;
static size_t fmincore_chunk_size;
static unsigned int advise_chunk;
static unsigned int max_bits;

/*
 * A HashSplitter is fed a file-like object and will determine
 * how the accumulated record stream should be split.
 */
typedef struct {
    PyObject_HEAD
    PyObject *files, *fobj;
    unsigned int bits;
    int filenum;
    int max_blob;
    int fd;
    PyObject *buf, *progress;
    int start, end, eof, bufsz;
    unsigned int boundaries, fanbits;
#ifdef HASHSPLITTER_ADVISE
    BUP_MINCORE_BUF_TYPE *mincore;
    size_t uncached, read;
#endif
} HashSplitter;

static int HashSplitter_allocbuf(HashSplitter *self)
{
    PyObject *buf = PyBytes_FromStringAndSize(NULL, self->bufsz);
    PyObject *oldbuf = self->buf;

    if (!buf) {
        PyErr_Format(PyExc_MemoryError, "cannot allocate %d bytes",
                     self->bufsz);
        return -1;
    }

    self->buf = buf;

    if (oldbuf) {
        memcpy(PyBytes_AS_STRING(self->buf),
               PyBytes_AS_STRING(oldbuf) + self->start,
               self->end - self->start);
        self->end -= self->start;
        self->start = 0;
        Py_DECREF(oldbuf);
    }

    return 0;
}

static int HashSplitter_nextfile(HashSplitter *self)
{
    PyObject *fd;
    long ifd;
#ifdef HASHSPLITTER_ADVISE
    struct stat s;
    unsigned int pages;
    off_t pos;
    unsigned int outoffs;

    self->uncached = 0;
    self->read = 0;

    free(self->mincore);
    self->mincore = NULL;
#endif

    Py_XDECREF(self->fobj);

    /* grab the next file */
    self->filenum++;
    self->fobj = PyIter_Next(self->files);
    if (!self->fobj) {
        if (PyErr_Occurred())
            return -1;
        return 0;
    }

    if (self->progress) {
        PyObject *o;

        // CAUTION: Py_XDECREF evaluates its argument twice!
        o = PyObject_CallFunction(self->progress, "ii", self->filenum, 0);
        Py_XDECREF(o);
    }

    self->fd = -1;
    self->eof = 0;
    fd = PyObject_CallMethod(self->fobj, "fileno", NULL);
    if (fd) {
        ifd = PyLong_AsLong(fd);
        Py_DECREF(fd);

        if (ifd == -1 && PyErr_Occurred())
            return -1;
        self->fd = ifd;

#ifdef HASHSPLITTER_ADVISE
        if (fstat(ifd, &s) < 0) {
            PyErr_Format(PyExc_IOError, "fstat failed");
            return -1;
        }

        pages = (s.st_size + page_size - 1) / page_size;
        self->mincore = malloc(pages);
        if (!self->mincore) {
            PyErr_Format(PyExc_MemoryError, "cannot allocate %d bytes",
                         pages);
            return -1;
        }

        Py_BEGIN_ALLOW_THREADS;

        for (outoffs = pos = 0;
             pos < s.st_size;
             pos += fmincore_chunk_size, outoffs += fmincore_chunk_size / page_size) {
             /* mmap in chunks and fill self->mincore */
             size_t len = s.st_size - pos;
             unsigned char *addr;
             int rc;

             if (len > fmincore_chunk_size)
                 len = fmincore_chunk_size;

             addr = mmap(NULL, len, PROT_NONE, MAP_PRIVATE, self->fd, pos);
             if (addr == MAP_FAILED) {
                 free(self->mincore);
                 self->mincore = NULL;
                 break;
             }

             rc = mincore(addr, len, self->mincore + outoffs);
             munmap(addr, len);

             if (rc < 0) {
                 free(self->mincore);
                 self->mincore = NULL;
                 break;
             }
        }

        Py_END_ALLOW_THREADS;
#endif
    } else {
        PyErr_Clear();
    }

    return 0;
}

static void HashSplitter_unref(HashSplitter *self)
{
    Py_XDECREF(self->buf);
    self->buf = NULL;
    Py_XDECREF(self->progress);
    self->progress = NULL;
    Py_XDECREF(self->fobj);
    self->fobj = NULL;
    Py_XDECREF(self->files);
    self->files = NULL;
#ifdef HASHSPLITTER_ADVISE
    free(self->mincore);
    self->mincore = NULL;
#endif
}

static int HashSplitter_init(HashSplitter *self, PyObject *args, PyObject *kwds)
{
    static char *argnames[] = {
        "files",
        "bits",
        "progress",
        "keep_boundaries",
        "fanbits",
        NULL
    };
    PyObject *files, *boundaries = NULL;

    self->start = 0;
    self->end = 0;
    self->progress = NULL;
    self->filenum = -1;
    self->fobj = NULL;
    self->boundaries = 1;
    self->fanbits = 4;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "Oi|OOi", argnames,
                                     &files, &self->bits,
                                     &self->progress, &boundaries,
                                     &self->fanbits))
        goto error;

    if (boundaries)
        self->boundaries = PyObject_IsTrue(boundaries);

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
        PyErr_Format(PyExc_ValueError,
                     "fanbits must be non-zero");
        goto error;
    }

    self->max_blob = 1 << (self->bits + 2);
    self->bufsz = advise_chunk;

    if (HashSplitter_allocbuf(self))
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

#ifdef HASHSPLITTER_ADVISE
static void HashSplitter_uncache(HashSplitter *self, int last)
{
    size_t len = self->read - self->uncached;
    unsigned int pgstart = self->uncached / page_size;
    unsigned int pages, i;
    size_t start;

    if (!self->mincore)
        return;

    if (!last) {
        len /= advise_chunk;
        len *= advise_chunk;
    }

    pages = len / page_size;

    // now track where and how much to uncache
    start = self->uncached;
    len = 0;

    for (i = 0; i < pages; i++) {
        if (self->mincore[pgstart + i] & HASHSPLITTER_MINCORE_INCORE) {
            if (len)
                posix_fadvise(self->fd, start, len, POSIX_FADV_DONTNEED);
            start += len + page_size;
            len = 0;
        } else {
            len += page_size;
        }
    }

    if (len)
	posix_fadvise(self->fd, start, len, POSIX_FADV_DONTNEED);

    self->uncached = start + len;
}
#endif

static int HashSplitter_read(HashSplitter *self)
{
    Py_ssize_t len;

    if (!self->fobj)
        return 0;

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
        self->read += len;

        if (len == 0 || self->read - self->uncached >= advise_chunk)
            HashSplitter_uncache(self, len == 0);
#endif
    } else {
        PyObject *r = PyObject_CallMethod(self->fobj, "read", "i",
                                          self->bufsz - self->end);
        Py_buffer buf;

        if (!r)
            return -1;

        if (PyObject_GetBuffer(r, &buf, PyBUF_FULL_RO)) {
            Py_DECREF(r);
            return -1;
        }

        len = buf.len;

        if (len > self->bufsz - self->end) {
            Py_DECREF(r);
            PyErr_Format(PyExc_ValueError,
                         "read(%d) returned %d bytes",
                         self->bufsz - self->end, (int)len);
            return -1;
        }

        if (len)
            PyBuffer_ToContiguous(PyBytes_AS_STRING(self->buf) + self->end,
                                  &buf, len, 'C');

        PyBuffer_Release(&buf);

        self->end += len;
        Py_DECREF(r);
    }

    if (self->progress && len) {
        PyObject *o;

        // CAUTION: Py_XDECREF evaluates its argument twice!
        o = PyObject_CallFunction(self->progress, "in", self->filenum, len);
        Py_XDECREF(o);
    }

    return len;
}

static int HashSplitter_find_offs(unsigned int nbits, const unsigned char *buf, int len,
                                  int *extrabits)
{
    PyThreadState *_save;
    Rollsum r;
    int count;
    unsigned short s2_mask = (1 << nbits) - 1;
    unsigned short s2_ones = ~0 & s2_mask;
    unsigned short s1_mask = 0;
    unsigned short s1_ones = 0;

    Py_UNBLOCK_THREADS;

    if (nbits > 16) {
        s1_mask = (1 << (nbits - 16)) - 1;
        s1_ones = ~0 & s1_mask;
    }

    rollsum_init(&r);

    for (count = 0; count < len; count++) {
        rollsum_roll(&r, buf[count]);

        if ((r.s2 & s2_mask) == s2_ones && (r.s1 & s1_mask) == s1_ones) {
            unsigned rsum = rollsum_digest(&r);

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

            Py_BLOCK_THREADS;
            return count + 1;
        }
    }

    Py_BLOCK_THREADS;
    return 0;
}

static PyObject *HashSplitter_iternext(HashSplitter *self)
{
    unsigned int nbits = self->bits;

    while (1) {
        const unsigned char *buf;
        int ofs, extrabits, maxlen, level;
        PyObject *ret;
        PyObject *mview;

        /* read some data if possible/needed */
        if (self->end < self->bufsz && self->fobj) {
            int rc;

            if (self->eof &&
                (!self->boundaries || self->start == self->end))
                HashSplitter_nextfile(self);

            rc = HashSplitter_read(self);

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

#define min(_a, _b) ((_a < _b) ? _a : _b)

        buf = (void *)PyBytes_AS_STRING(self->buf);
        maxlen = min(self->end - self->start, self->max_blob);

        ofs = HashSplitter_find_offs(nbits, buf + self->start, maxlen,
                                     &extrabits);

        if (ofs) {
            level = extrabits / self->fanbits;
        } else if (self->start + self->max_blob <= self->end) {
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
            if (HashSplitter_allocbuf(self))
                return NULL;
            continue;
        }

        /* return the found chunk as a buffer view into the total */
        mview = PyMemoryView_FromObject(self->buf);
        ret = PySequence_GetSlice(mview, self->start, self->start + ofs);
        Py_DECREF(mview);
        self->start += ofs;
        return Py_BuildValue("Ni", ret, level);
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
    size_t pref_chunk_size = 64 * 1024 * 1024;

    page_size = sysconf(_SC_PAGESIZE);

    if (page_size < 0) {
        PyErr_SetFromErrno(PyExc_OSError);
        return -1;
    }

    fmincore_chunk_size = page_size;

    if (fmincore_chunk_size < pref_chunk_size)
        fmincore_chunk_size = page_size * (pref_chunk_size / page_size);

    advise_chunk = 8 * 1024 * 1024;
    /*
     * We read in advise_chunk blocks too, so max_blob cannot be
     * bigger than that, but max_blob is 4 << bits, so calculate
     * max_bits that way.
     */
    max_bits = log2(advise_chunk) - 2;
    if (page_size > advise_chunk)
        advise_chunk = page_size;

    if (PyType_Ready(&HashSplitterType) < 0)
        return -1;

    return 0;
}
