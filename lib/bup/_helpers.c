#define _LARGEFILE64_SOURCE 1
#define PY_SSIZE_T_CLEAN 1
#undef NDEBUG
#include "../../config/config.h"

// According to Python, its header has to go first:
//   http://docs.python.org/2/c-api/intro.html#include-files
#include <Python.h>

#include <arpa/inet.h>
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <pwd.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

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
#ifdef HAVE_SYS_TIME_H
#include <sys/time.h>
#endif

#ifdef HAVE_LINUX_FS_H
#include <linux/fs.h>
#endif
#ifdef HAVE_SYS_IOCTL_H
#include <sys/ioctl.h>
#endif

#ifdef HAVE_TM_TM_GMTOFF
#include <time.h>
#endif

#include "bupsplit.h"

#if defined(FS_IOC_GETFLAGS) && defined(FS_IOC_SETFLAGS)
#define BUP_HAVE_FILE_ATTRS 1
#endif

/*
 * Check for incomplete UTIMENSAT support (NetBSD 6), and if so,
 * pretend we don't have it.
 */
#if !defined(AT_FDCWD) || !defined(AT_SYMLINK_NOFOLLOW)
#undef HAVE_UTIMENSAT
#endif

#ifndef FS_NOCOW_FL
// Of course, this assumes it's a bitfield value.
#define FS_NOCOW_FL 0
#endif


typedef unsigned char byte;


typedef struct {
    int istty2;
} state_t;

// cstr_argf: for byte vectors without null characters (e.g. paths)
// rbuf_argf: for read-only byte vectors
// wbuf_argf: for mutable byte vectors

#if PY_MAJOR_VERSION < 3
static state_t state;
#  define get_state(x) (&state)
#  define cstr_argf "s"
#  define rbuf_argf "s#"
#  define wbuf_argf "s*"
#else
#  define get_state(x) ((state_t *) PyModule_GetState(x))
#  define cstr_argf "y"
#  define rbuf_argf "y#"
#  define wbuf_argf "y*"
#endif // PY_MAJOR_VERSION >= 3


static void *checked_calloc(size_t n, size_t size)
{
    void *result = calloc(n, size);
    if (!result)
        PyErr_NoMemory();
    return result;
}

#ifndef BUP_HAVE_BUILTIN_MUL_OVERFLOW

#define checked_malloc checked_calloc

#else // defined BUP_HAVE_BUILTIN_MUL_OVERFLOW

static void *checked_malloc(size_t n, size_t size)
{
    size_t total;
    if (__builtin_mul_overflow(n, size, &total))
    {
        PyErr_Format(PyExc_OverflowError,
                     "request to allocate %lu items of size %lu is too large",
                     n, size);
        return NULL;
    }
    void *result = malloc(total);
    if (!result)
        return PyErr_NoMemory();
    return result;
}

#endif // defined BUP_HAVE_BUILTIN_MUL_OVERFLOW


#ifndef htonll
// This function should technically be macro'd out if it's going to be used
// more than ocasionally.  As of this writing, it'll actually never be called
// in real world bup scenarios (because our packs are < MAX_INT bytes).
static uint64_t htonll(uint64_t value)
{
    static const int endian_test = 42;

    if (*(char *)&endian_test == endian_test) // LSB-MSB
	return ((uint64_t)htonl(value & 0xFFFFFFFF) << 32) | htonl(value >> 32);
    return value; // already in network byte order MSB-LSB
}
#endif


// Disabling sign-compare here should be fine since we're explicitly
// checking for a sign mismatch, i.e. if the signs don't match, then
// it doesn't matter what the value comparison says.
// FIXME: ... so should we reverse the order?
#define INTEGRAL_ASSIGNMENT_FITS(dest, src)                             \
    ({                                                                  \
        _Pragma("GCC diagnostic push");                                 \
        _Pragma("GCC diagnostic ignored \"-Wsign-compare\"");           \
        *(dest) = (src);                                                \
        int result = *(dest) == (src) && (*(dest) < 1) == ((src) < 1);  \
        _Pragma("GCC diagnostic pop");                                  \
        result;                                                         \
    })


// At the moment any code that calls INTEGER_TO_PY() will have to
// disable -Wtautological-compare for clang.  See below.

#define INTEGER_TO_PY(x) \
    (((x) >= 0) ? PyLong_FromUnsignedLongLong(x) : PyLong_FromLongLong(x))



#if PY_MAJOR_VERSION < 3
static int bup_ulong_from_pyint(unsigned long *x, PyObject *py,
                                const char *name)
{
    const long tmp = PyInt_AsLong(py);
    if (tmp == -1 && PyErr_Occurred())
    {
        if (PyErr_ExceptionMatches(PyExc_OverflowError))
            PyErr_Format(PyExc_OverflowError, "%s too big for unsigned long",
                         name);
        return 0;
    }
    if (tmp < 0)
    {
        PyErr_Format(PyExc_OverflowError,
                     "negative %s cannot be converted to unsigned long", name);
        return 0;
    }
    *x = tmp;
    return 1;
}
#endif


static int bup_ulong_from_py(unsigned long *x, PyObject *py, const char *name)
{
#if PY_MAJOR_VERSION < 3
    if (PyInt_Check(py))
        return bup_ulong_from_pyint(x, py, name);
#endif

    if (!PyLong_Check(py))
    {
        PyErr_Format(PyExc_TypeError, "expected integer %s", name);
        return 0;
    }

    const unsigned long tmp = PyLong_AsUnsignedLong(py);
    if (PyErr_Occurred())
    {
        if (PyErr_ExceptionMatches(PyExc_OverflowError))
            PyErr_Format(PyExc_OverflowError, "%s too big for unsigned long",
                         name);
        return 0;
    }
    *x = tmp;
    return 1;
}


static int bup_uint_from_py(unsigned int *x, PyObject *py, const char *name)
{
    unsigned long tmp;
    if (!bup_ulong_from_py(&tmp, py, name))
        return 0;

    if (tmp > UINT_MAX)
    {
        PyErr_Format(PyExc_OverflowError, "%s too big for unsigned int", name);
        return 0;
    }
    *x = tmp;
    return 1;
}

static int bup_ullong_from_py(unsigned PY_LONG_LONG *x, PyObject *py,
                              const char *name)
{
#if PY_MAJOR_VERSION < 3
    if (PyInt_Check(py))
    {
        unsigned long tmp;
        if (bup_ulong_from_pyint(&tmp, py, name))
        {
            *x = tmp;
            return 1;
        }
        return 0;
    }
#endif

    if (!PyLong_Check(py))
    {
        PyErr_Format(PyExc_TypeError, "integer argument expected for %s", name);
        return 0;
    }

    const unsigned PY_LONG_LONG tmp = PyLong_AsUnsignedLongLong(py);
    if (tmp == (unsigned long long) -1 && PyErr_Occurred())
    {
        if (PyErr_ExceptionMatches(PyExc_OverflowError))
            PyErr_Format(PyExc_OverflowError,
                         "%s too big for unsigned long long", name);
        return 0;
    }
    *x = tmp;
    return 1;
}


static PyObject *bup_bytescmp(PyObject *self, PyObject *args)
{
    PyObject *py_s1, *py_s2;  // This is really a PyBytes/PyString
    if (!PyArg_ParseTuple(args, "SS", &py_s1, &py_s2))
	return NULL;
    char *s1, *s2;
    Py_ssize_t s1_len, s2_len;
    if (PyBytes_AsStringAndSize(py_s1, &s1, &s1_len) == -1)
        return NULL;
    if (PyBytes_AsStringAndSize(py_s2, &s2, &s2_len) == -1)
        return NULL;
    const Py_ssize_t n = (s1_len < s2_len) ? s1_len : s2_len;
    const int cmp = memcmp(s1, s2, n);
    if (cmp != 0)
        return PyLong_FromLong(cmp);
    if (s1_len == s2_len)
        return PyLong_FromLong(0);;
    return PyLong_FromLong((s1_len < s2_len) ? -1 : 1);
}


static PyObject *bup_cat_bytes(PyObject *self, PyObject *args)
{
    unsigned char *bufx = NULL, *bufy = NULL;
    Py_ssize_t bufx_len, bufx_ofs, bufx_n;
    Py_ssize_t bufy_len, bufy_ofs, bufy_n;
    if (!PyArg_ParseTuple(args,
                          rbuf_argf "nn"
                          rbuf_argf "nn",
                          &bufx, &bufx_len, &bufx_ofs, &bufx_n,
                          &bufy, &bufy_len, &bufy_ofs, &bufy_n))
	return NULL;
    if (bufx_ofs < 0)
        return PyErr_Format(PyExc_ValueError, "negative x offset");
    if (bufx_n < 0)
        return PyErr_Format(PyExc_ValueError, "negative x extent");
    if (bufx_ofs > bufx_len)
        return PyErr_Format(PyExc_ValueError, "x offset greater than length");
    if (bufx_n > bufx_len - bufx_ofs)
        return PyErr_Format(PyExc_ValueError, "x extent past end of buffer");

    if (bufy_ofs < 0)
        return PyErr_Format(PyExc_ValueError, "negative y offset");
    if (bufy_n < 0)
        return PyErr_Format(PyExc_ValueError, "negative y extent");
    if (bufy_ofs > bufy_len)
        return PyErr_Format(PyExc_ValueError, "y offset greater than length");
    if (bufy_n > bufy_len - bufy_ofs)
        return PyErr_Format(PyExc_ValueError, "y extent past end of buffer");

    if (bufy_n > PY_SSIZE_T_MAX - bufx_n)
        return PyErr_Format(PyExc_OverflowError, "result length too long");

    PyObject *result = PyBytes_FromStringAndSize(NULL, bufx_n + bufy_n);
    if (!result)
        return PyErr_NoMemory();
    char *buf = PyBytes_AS_STRING(result);
    memcpy(buf, bufx + bufx_ofs, bufx_n);
    memcpy(buf + bufx_n, bufy + bufy_ofs, bufy_n);
    return result;
}



// Probably we should use autoconf or something and set HAVE_PY_GETARGCARGV...
#if __WIN32__ || __CYGWIN__

// There's no 'ps' on win32 anyway, and Py_GetArgcArgv() isn't available.
static void unpythonize_argv(void) { }

#else // not __WIN32__

// For some reason this isn't declared in Python.h
extern void Py_GetArgcArgv(int *argc, char ***argv);

static void unpythonize_argv(void)
{
    int argc, i;
    char **argv, *arge;
    
    Py_GetArgcArgv(&argc, &argv);
    
    for (i = 0; i < argc-1; i++)
    {
	if (argv[i] + strlen(argv[i]) + 1 != argv[i+1])
	{
	    // The argv block doesn't work the way we expected; it's unsafe
	    // to mess with it.
	    return;
	}
    }
    
    arge = argv[argc-1] + strlen(argv[argc-1]) + 1;
    
    if (strstr(argv[0], "python") && argv[1] == argv[0] + strlen(argv[0]) + 1)
    {
	char *p;
	size_t len, diff;
	p = strrchr(argv[1], '/');
	if (p)
	{
	    p++;
	    diff = p - argv[0];
	    len = arge - p;
	    memmove(argv[0], p, len);
	    memset(arge - diff, 0, diff);
	    for (i = 0; i < argc; i++)
		argv[i] = argv[i+1] ? argv[i+1]-diff : NULL;
	}
    }
}

#endif // not __WIN32__ or __CYGWIN__


static int write_all(int fd, const void *buf, const size_t count)
{
    size_t written = 0;
    while (written < count)
    {
        const ssize_t rc = write(fd, buf + written, count - written);
        if (rc == -1)
            return -1;
        written += rc;
    }
    return 0;
}


static int uadd(unsigned long long *dest,
                const unsigned long long x,
                const unsigned long long y)
{
    const unsigned long long result = x + y;
    if (result < x || result < y)
        return 0;
    *dest = result;
    return 1;
}


static PyObject *append_sparse_region(const int fd, unsigned long long n)
{
    while (n)
    {
        off_t new_off;
        if (!INTEGRAL_ASSIGNMENT_FITS(&new_off, n))
            new_off = INT_MAX;
        const off_t off = lseek(fd, new_off, SEEK_CUR);
        if (off == (off_t) -1)
            return PyErr_SetFromErrno(PyExc_IOError);
        n -= new_off;
    }
    return NULL;
}


static PyObject *record_sparse_zeros(unsigned long long *new_pending,
                                     const int fd,
                                     unsigned long long prev_pending,
                                     const unsigned long long count)
{
    // Add count additional sparse zeros to prev_pending and store the
    // result in new_pending, or if the total won't fit in
    // new_pending, write some of the zeros to fd sparsely, and store
    // the remaining sum in new_pending.
    if (!uadd(new_pending, prev_pending, count))
    {
        PyObject *err = append_sparse_region(fd, prev_pending);
        if (err != NULL)
            return err;
        *new_pending = count;
    }
    return NULL;
}


static byte* find_not_zero(const byte * const start, const byte * const end)
{
    // Return a pointer to first non-zero byte between start and end,
    // or end if there isn't one.
    assert(start <= end);
    const unsigned char *cur = start;
    while (cur < end && *cur == 0)
        cur++;
    return (byte *) cur;
}


static byte* find_trailing_zeros(const byte * const start,
                                 const byte * const end)
{
    // Return a pointer to the start of any trailing run of zeros, or
    // end if there isn't one.
    assert(start <= end);
    if (start == end)
        return (byte *) end;
    const byte * cur = end;
    while (cur > start && *--cur == 0) {}
    if (*cur == 0)
        return (byte *) cur;
    else
        return (byte *) (cur + 1);
}


static byte *find_non_sparse_end(const byte * const start,
                                 const byte * const end,
                                 const ptrdiff_t min_len)
{
    // Return the first pointer to a min_len sparse block in [start,
    // end) if there is one, otherwise a pointer to the start of any
    // trailing run of zeros.  If there are no trailing zeros, return
    // end.
    if (start == end)
        return (byte *) end;
    assert(start < end);
    assert(min_len);
    // Probe in min_len jumps, searching backward from the jump
    // destination for a non-zero byte.  If such a byte is found, move
    // just past it and try again.
    const byte *candidate = start;
    // End of any run of zeros, starting at candidate, that we've already seen
    const byte *end_of_known_zeros = candidate;
    while (end - candidate >= min_len) // Handle all min_len candidate blocks
    {
        const byte * const probe_end = candidate + min_len;
        const byte * const trailing_zeros =
            find_trailing_zeros(end_of_known_zeros, probe_end);
        if (trailing_zeros == probe_end)
            end_of_known_zeros = candidate = probe_end;
        else if (trailing_zeros == end_of_known_zeros)
        {
            assert(candidate >= start);
            assert(candidate <= end);
            assert(*candidate == 0);
            return (byte *) candidate;
        }
        else
        {
            candidate = trailing_zeros;
            end_of_known_zeros = probe_end;
        }
    }

    if (candidate == end)
        return (byte *) end;

    // No min_len sparse run found, search backward from end
    const byte * const trailing_zeros = find_trailing_zeros(end_of_known_zeros,
                                                            end);

    if (trailing_zeros == end_of_known_zeros)
    {
        assert(candidate >= start);
        assert(candidate < end);
        assert(*candidate == 0);
        assert(end - candidate < min_len);
        return (byte *) candidate;
    }

    if (trailing_zeros == end)
    {
        assert(*(end - 1) != 0);
        return (byte *) end;
    }

    assert(end - trailing_zeros < min_len);
    assert(trailing_zeros >= start);
    assert(trailing_zeros < end);
    assert(*trailing_zeros == 0);
    return (byte *) trailing_zeros;
}


static PyObject *bup_write_sparsely(PyObject *self, PyObject *args)
{
    int fd;
    unsigned char *buf = NULL;
    Py_ssize_t sbuf_len;
    PyObject *py_min_sparse_len, *py_prev_sparse_len;
    if (!PyArg_ParseTuple(args, "i" rbuf_argf "OO",
                          &fd, &buf, &sbuf_len,
                          &py_min_sparse_len, &py_prev_sparse_len))
	return NULL;
    ptrdiff_t min_sparse_len;
    unsigned long long prev_sparse_len, buf_len, ul_min_sparse_len;
    if (!bup_ullong_from_py(&ul_min_sparse_len, py_min_sparse_len, "min_sparse_len"))
        return NULL;
    if (!INTEGRAL_ASSIGNMENT_FITS(&min_sparse_len, ul_min_sparse_len))
        return PyErr_Format(PyExc_OverflowError, "min_sparse_len too large");
    if (!bup_ullong_from_py(&prev_sparse_len, py_prev_sparse_len, "prev_sparse_len"))
        return NULL;
    if (sbuf_len < 0)
        return PyErr_Format(PyExc_ValueError, "negative bufer length");
    if (!INTEGRAL_ASSIGNMENT_FITS(&buf_len, sbuf_len))
        return PyErr_Format(PyExc_OverflowError, "buffer length too large");

    const byte * block = buf; // Start of pending block
    const byte * const end = buf + buf_len;
    unsigned long long zeros = prev_sparse_len;
    while (1)
    {
        assert(block <= end);
        if (block == end)
            return PyLong_FromUnsignedLongLong(zeros);

        if (*block != 0)
        {
            // Look for the end of block, i.e. the next sparse run of
            // at least min_sparse_len zeros, or the end of the
            // buffer.
            const byte * const probe = find_non_sparse_end(block + 1, end,
                                                           min_sparse_len);
            // Either at end of block, or end of non-sparse; write pending data
            PyObject *err = append_sparse_region(fd, zeros);
            if (err != NULL)
                return err;
            int rc = write_all(fd, block, probe - block);
            if (rc)
                return PyErr_SetFromErrno(PyExc_IOError);

            if (end - probe < min_sparse_len)
                zeros = end - probe;
            else
                zeros = min_sparse_len;
            block = probe + zeros;
        }
        else // *block == 0
        {
            // Should be in the first loop iteration, a sparse run of
            // zeros, or nearly at the end of the block (within
            // min_sparse_len).
            const byte * const zeros_end = find_not_zero(block, end);
            PyObject *err = record_sparse_zeros(&zeros, fd,
                                                zeros, zeros_end - block);
            if (err != NULL)
                return err;
            assert(block <= zeros_end);
            block = zeros_end;
        }
    }
}


static PyObject *selftest(PyObject *self, PyObject *args)
{
    if (!PyArg_ParseTuple(args, ""))
	return NULL;
    
    return Py_BuildValue("i", !bupsplit_selftest());
}


static PyObject *blobbits(PyObject *self, PyObject *args)
{
    if (!PyArg_ParseTuple(args, ""))
	return NULL;
    return Py_BuildValue("i", BUP_BLOBBITS);
}


static PyObject *splitbuf(PyObject *self, PyObject *args)
{
    // We stick to buffers in python 2 because they appear to be
    // substantially smaller than memoryviews, and because
    // zlib.compress() in python 2 can't accept a memoryview
    // (cf. hashsplit.py).
    int out = 0, bits = -1;
    if (PY_MAJOR_VERSION > 2)
    {
        Py_buffer buf;
        if (!PyArg_ParseTuple(args, "y*", &buf))
            return NULL;
        assert(buf.len <= INT_MAX);
        out = bupsplit_find_ofs(buf.buf, buf.len, &bits);
        PyBuffer_Release(&buf);
    }
    else
    {
        unsigned char *buf = NULL;
        Py_ssize_t len = 0;
        if (!PyArg_ParseTuple(args, "t#", &buf, &len))
            return NULL;
        assert(len <= INT_MAX);
        out = bupsplit_find_ofs(buf, len, &bits);
    }
    if (out) assert(bits >= BUP_BLOBBITS);
    return Py_BuildValue("ii", out, bits);
}


static PyObject *bitmatch(PyObject *self, PyObject *args)
{
    unsigned char *buf1 = NULL, *buf2 = NULL;
    Py_ssize_t len1 = 0, len2 = 0;
    Py_ssize_t byte;
    int bit;

    if (!PyArg_ParseTuple(args, rbuf_argf rbuf_argf, &buf1, &len1, &buf2, &len2))
	return NULL;
    
    bit = 0;
    for (byte = 0; byte < len1 && byte < len2; byte++)
    {
	int b1 = buf1[byte], b2 = buf2[byte];
	if (b1 != b2)
	{
	    for (bit = 0; bit < 8; bit++)
		if ( (b1 & (0x80 >> bit)) != (b2 & (0x80 >> bit)) )
		    break;
	    break;
	}
    }
    
    assert(byte <= (INT_MAX >> 3));
    return Py_BuildValue("i", byte*8 + bit);
}


static PyObject *firstword(PyObject *self, PyObject *args)
{
    unsigned char *buf = NULL;
    Py_ssize_t len = 0;
    uint32_t v;

    if (!PyArg_ParseTuple(args, rbuf_argf, &buf, &len))
	return NULL;
    
    if (len < 4)
	return NULL;
    
    v = ntohl(*(uint32_t *)buf);
    return PyLong_FromUnsignedLong(v);
}


#define BLOOM2_HEADERLEN 16

static void to_bloom_address_bitmask4(const unsigned char *buf,
	const int nbits, uint64_t *v, unsigned char *bitmask)
{
    int bit;
    uint32_t high;
    uint64_t raw, mask;

    memcpy(&high, buf, 4);
    mask = (1<<nbits) - 1;
    raw = (((uint64_t)ntohl(high) << 8) | buf[4]);
    bit = (raw >> (37-nbits)) & 0x7;
    *v = (raw >> (40-nbits)) & mask;
    *bitmask = 1 << bit;
}

static void to_bloom_address_bitmask5(const unsigned char *buf,
	const int nbits, uint32_t *v, unsigned char *bitmask)
{
    int bit;
    uint32_t high;
    uint32_t raw, mask;

    memcpy(&high, buf, 4);
    mask = (1<<nbits) - 1;
    raw = ntohl(high);
    bit = (raw >> (29-nbits)) & 0x7;
    *v = (raw >> (32-nbits)) & mask;
    *bitmask = 1 << bit;
}

#define BLOOM_SET_BIT(name, address, otype) \
static void name(unsigned char *bloom, const unsigned char *buf, const int nbits)\
{\
    unsigned char bitmask;\
    otype v;\
    address(buf, nbits, &v, &bitmask);\
    bloom[BLOOM2_HEADERLEN+v] |= bitmask;\
}
BLOOM_SET_BIT(bloom_set_bit4, to_bloom_address_bitmask4, uint64_t)
BLOOM_SET_BIT(bloom_set_bit5, to_bloom_address_bitmask5, uint32_t)


#define BLOOM_GET_BIT(name, address, otype) \
static int name(const unsigned char *bloom, const unsigned char *buf, const int nbits)\
{\
    unsigned char bitmask;\
    otype v;\
    address(buf, nbits, &v, &bitmask);\
    return bloom[BLOOM2_HEADERLEN+v] & bitmask;\
}
BLOOM_GET_BIT(bloom_get_bit4, to_bloom_address_bitmask4, uint64_t)
BLOOM_GET_BIT(bloom_get_bit5, to_bloom_address_bitmask5, uint32_t)


static PyObject *bloom_add(PyObject *self, PyObject *args)
{
    Py_buffer bloom, sha;
    int nbits = 0, k = 0;
    if (!PyArg_ParseTuple(args, wbuf_argf wbuf_argf "ii",
                          &bloom, &sha, &nbits, &k))
        return NULL;

    PyObject *result = NULL;

    if (bloom.len < 16+(1<<nbits) || sha.len % 20 != 0)
        goto clean_and_return;

    if (k == 5)
    {
        if (nbits > 29)
            goto clean_and_return;
        unsigned char *cur = sha.buf;
        unsigned char *end;
        for (end = cur + sha.len; cur < end; cur += 20/k)
            bloom_set_bit5(bloom.buf, cur, nbits);
    }
    else if (k == 4)
    {
        if (nbits > 37)
            goto clean_and_return;
        unsigned char *cur = sha.buf;
        unsigned char *end = cur + sha.len;
        for (; cur < end; cur += 20/k)
            bloom_set_bit4(bloom.buf, cur, nbits);
    }
    else
        goto clean_and_return;

    result = Py_BuildValue("n", sha.len / 20);

 clean_and_return:
    PyBuffer_Release(&bloom);
    PyBuffer_Release(&sha);
    return result;
}

static PyObject *bloom_contains(PyObject *self, PyObject *args)
{
    Py_buffer bloom;
    unsigned char *sha = NULL;
    Py_ssize_t len = 0;
    int nbits = 0, k = 0;
    if (!PyArg_ParseTuple(args, wbuf_argf rbuf_argf "ii",
                          &bloom, &sha, &len, &nbits, &k))
        return NULL;

    PyObject *result = NULL;

    if (len != 20)
        goto clean_and_return;

    if (k == 5)
    {
        if (nbits > 29)
            goto clean_and_return;
        int steps;
        unsigned char *end;
        for (steps = 1, end = sha + 20; sha < end; sha += 20/k, steps++)
            if (!bloom_get_bit5(bloom.buf, sha, nbits))
            {
                result = Py_BuildValue("Oi", Py_None, steps);
                goto clean_and_return;
            }
    }
    else if (k == 4)
    {
        if (nbits > 37)
            goto clean_and_return;
        int steps;
        unsigned char *end;
        for (steps = 1, end = sha + 20; sha < end; sha += 20/k, steps++)
            if (!bloom_get_bit4(bloom.buf, sha, nbits))
            {
                result = Py_BuildValue("Oi", Py_None, steps);
                goto clean_and_return;
            }
    }
    else
        goto clean_and_return;

    result = Py_BuildValue("ii", 1, k);

 clean_and_return:
    PyBuffer_Release(&bloom);
    return result;
}


static uint32_t _extract_bits(unsigned char *buf, int nbits)
{
    uint32_t v, mask;

    mask = (1<<nbits) - 1;
    v = ntohl(*(uint32_t *)buf);
    v = (v >> (32-nbits)) & mask;
    return v;
}


static PyObject *extract_bits(PyObject *self, PyObject *args)
{
    unsigned char *buf = NULL;
    Py_ssize_t len = 0;
    int nbits = 0;

    if (!PyArg_ParseTuple(args, rbuf_argf "i", &buf, &len, &nbits))
	return NULL;
    
    if (len < 4)
	return NULL;
    
    return PyLong_FromUnsignedLong(_extract_bits(buf, nbits));
}


struct sha {
    unsigned char bytes[20];
};

static inline int _cmp_sha(const struct sha *sha1, const struct sha *sha2)
{
    return memcmp(sha1->bytes, sha2->bytes, sizeof(sha1->bytes));
}


struct idx {
    unsigned char *map;
    struct sha *cur;
    struct sha *end;
    uint32_t *cur_name;
    Py_ssize_t bytes;
    int name_base;
};

static void _fix_idx_order(struct idx **idxs, Py_ssize_t *last_i)
{
    struct idx *idx;
    int low, mid, high, c = 0;

    idx = idxs[*last_i];
    if (idxs[*last_i]->cur >= idxs[*last_i]->end)
    {
	idxs[*last_i] = NULL;
	PyMem_Free(idx);
	--*last_i;
	return;
    }
    if (*last_i == 0)
	return;

    low = *last_i-1;
    mid = *last_i;
    high = 0;
    while (low >= high)
    {
	mid = (low + high) / 2;
	c = _cmp_sha(idx->cur, idxs[mid]->cur);
	if (c < 0)
	    high = mid + 1;
	else if (c > 0)
	    low = mid - 1;
	else
	    break;
    }
    if (c < 0)
	++mid;
    if (mid == *last_i)
	return;
    memmove(&idxs[mid+1], &idxs[mid], (*last_i-mid)*sizeof(struct idx *));
    idxs[mid] = idx;
}


static uint32_t _get_idx_i(struct idx *idx)
{
    if (idx->cur_name == NULL)
	return idx->name_base;
    return ntohl(*idx->cur_name) + idx->name_base;
}

#define MIDX4_HEADERLEN 12

static PyObject *merge_into(PyObject *self, PyObject *args)
{
    struct sha *sha_ptr, *sha_start = NULL;
    uint32_t *table_ptr, *name_ptr, *name_start;
    int i;
    unsigned int total;
    uint32_t count, prefix;


    Py_buffer fmap;
    int bits;;
    PyObject *py_total, *ilist = NULL;
    if (!PyArg_ParseTuple(args, wbuf_argf "iOO",
                          &fmap, &bits, &py_total, &ilist))
	return NULL;

    PyObject *result = NULL;
    struct idx **idxs = NULL;
    Py_ssize_t num_i = 0;
    int *idx_buf_init = NULL;
    Py_buffer *idx_buf = NULL;

    if (!bup_uint_from_py(&total, py_total, "total"))
        goto clean_and_return;

    num_i = PyList_Size(ilist);

    if (!(idxs = checked_malloc(num_i, sizeof(struct idx *))))
        goto clean_and_return;
    if (!(idx_buf_init = checked_calloc(num_i, sizeof(int))))
        goto clean_and_return;
    if (!(idx_buf = checked_malloc(num_i, sizeof(Py_buffer))))
        goto clean_and_return;

    for (i = 0; i < num_i; i++)
    {
	long len, sha_ofs, name_map_ofs;
	if (!(idxs[i] = checked_malloc(1, sizeof(struct idx))))
            goto clean_and_return;
	PyObject *itup = PyList_GetItem(ilist, i);
	if (!PyArg_ParseTuple(itup, wbuf_argf "llli",
                              &(idx_buf[i]), &len, &sha_ofs, &name_map_ofs,
                              &idxs[i]->name_base))
	    return NULL;
        idx_buf_init[i] = 1;
        idxs[i]->map = idx_buf[i].buf;
        idxs[i]->bytes = idx_buf[i].len;
	idxs[i]->cur = (struct sha *)&idxs[i]->map[sha_ofs];
	idxs[i]->end = &idxs[i]->cur[len];
	if (name_map_ofs)
	    idxs[i]->cur_name = (uint32_t *)&idxs[i]->map[name_map_ofs];
	else
	    idxs[i]->cur_name = NULL;
    }
    table_ptr = (uint32_t *) &((unsigned char *) fmap.buf)[MIDX4_HEADERLEN];
    sha_start = sha_ptr = (struct sha *)&table_ptr[1<<bits];
    name_start = name_ptr = (uint32_t *)&sha_ptr[total];

    Py_ssize_t last_i = num_i - 1;
    count = 0;
    prefix = 0;
    while (last_i >= 0)
    {
	struct idx *idx;
	uint32_t new_prefix;
	if (count % 102424 == 0 && get_state(self)->istty2)
	    fprintf(stderr, "midx: writing %.2f%% (%d/%d)\r",
		    count*100.0/total, count, total);
	idx = idxs[last_i];
	new_prefix = _extract_bits((unsigned char *)idx->cur, bits);
	while (prefix < new_prefix)
	    table_ptr[prefix++] = htonl(count);
	memcpy(sha_ptr++, idx->cur, sizeof(struct sha));
	*name_ptr++ = htonl(_get_idx_i(idx));
	++idx->cur;
	if (idx->cur_name != NULL)
	    ++idx->cur_name;
	_fix_idx_order(idxs, &last_i);
	++count;
    }
    while (prefix < ((uint32_t) 1 << bits))
	table_ptr[prefix++] = htonl(count);
    assert(count == total);
    assert(prefix == ((uint32_t) 1 << bits));
    assert(sha_ptr == sha_start+count);
    assert(name_ptr == name_start+count);

    result = PyLong_FromUnsignedLong(count);

 clean_and_return:
    if (idx_buf_init)
    {
        for (i = 0; i < num_i; i++)
            if (idx_buf_init[i])
                PyBuffer_Release(&(idx_buf[i]));
        free(idx_buf_init);
        free(idx_buf);
    }
    if (idxs)
    {
        for (i = 0; i < num_i; i++)
            free(idxs[i]);
        free(idxs);
    }
    PyBuffer_Release(&fmap);
    return result;
}

#define FAN_ENTRIES 256

static PyObject *write_idx(PyObject *self, PyObject *args)
{
    char *filename = NULL;
    PyObject *py_total, *idx = NULL;
    PyObject *part;
    unsigned int total = 0;
    uint32_t count;
    int i, j, ofs64_count;
    uint32_t *fan_ptr, *crc_ptr, *ofs_ptr;
    uint64_t *ofs64_ptr;
    struct sha *sha_ptr;

    Py_buffer fmap;
    if (!PyArg_ParseTuple(args, cstr_argf wbuf_argf "OO",
                          &filename, &fmap, &idx, &py_total))
	return NULL;

    PyObject *result = NULL;

    if (!bup_uint_from_py(&total, py_total, "total"))
        goto clean_and_return;

    if (PyList_Size (idx) != FAN_ENTRIES) // Check for list of the right length.
    {
        result = PyErr_Format (PyExc_TypeError, "idx must contain %d entries",
                               FAN_ENTRIES);
        goto clean_and_return;
    }

    const char idx_header[] = "\377tOc\0\0\0\002";
    memcpy (fmap.buf, idx_header, sizeof(idx_header) - 1);

    fan_ptr = (uint32_t *)&((unsigned char *)fmap.buf)[sizeof(idx_header) - 1];
    sha_ptr = (struct sha *)&fan_ptr[FAN_ENTRIES];
    crc_ptr = (uint32_t *)&sha_ptr[total];
    ofs_ptr = (uint32_t *)&crc_ptr[total];
    ofs64_ptr = (uint64_t *)&ofs_ptr[total];

    count = 0;
    ofs64_count = 0;
    for (i = 0; i < FAN_ENTRIES; ++i)
    {
	int plen;
	part = PyList_GET_ITEM(idx, i);
	PyList_Sort(part);
	plen = PyList_GET_SIZE(part);
	count += plen;
	*fan_ptr++ = htonl(count);
	for (j = 0; j < plen; ++j)
	{
	    unsigned char *sha = NULL;
	    Py_ssize_t sha_len = 0;
            PyObject *crc_py, *ofs_py;
	    unsigned int crc;
            unsigned PY_LONG_LONG ofs_ull;
	    uint64_t ofs;
	    if (!PyArg_ParseTuple(PyList_GET_ITEM(part, j), rbuf_argf "OO",
				  &sha, &sha_len, &crc_py, &ofs_py))
                goto clean_and_return;
            if(!bup_uint_from_py(&crc, crc_py, "crc"))
                goto clean_and_return;
            if(!bup_ullong_from_py(&ofs_ull, ofs_py, "ofs"))
                goto clean_and_return;
            assert(crc <= UINT32_MAX);
            assert(ofs_ull <= UINT64_MAX);
	    ofs = ofs_ull;
	    if (sha_len != sizeof(struct sha))
                goto clean_and_return;
	    memcpy(sha_ptr++, sha, sizeof(struct sha));
	    *crc_ptr++ = htonl(crc);
	    if (ofs > 0x7fffffff)
	    {
                *ofs64_ptr++ = htonll(ofs);
		ofs = 0x80000000 | ofs64_count++;
	    }
	    *ofs_ptr++ = htonl((uint32_t)ofs);
	}
    }

    int rc = msync(fmap.buf, fmap.len, MS_ASYNC);
    if (rc != 0)
    {
        result = PyErr_SetFromErrnoWithFilename(PyExc_IOError, filename);
        goto clean_and_return;
    }

    result = PyLong_FromUnsignedLong(count);

 clean_and_return:
    PyBuffer_Release(&fmap);
    return result;
}


// I would have made this a lower-level function that just fills in a buffer
// with random values, and then written those values from python.  But that's
// about 20% slower in my tests, and since we typically generate random
// numbers for benchmarking other parts of bup, any slowness in generating
// random bytes will make our benchmarks inaccurate.  Plus nobody wants
// pseudorandom bytes much except for this anyway.
static PyObject *write_random(PyObject *self, PyObject *args)
{
    uint32_t buf[1024/4];
    int fd = -1, seed = 0, verbose = 0;
    ssize_t ret;
    long long len = 0, kbytes = 0, written = 0;

    if (!PyArg_ParseTuple(args, "iLii", &fd, &len, &seed, &verbose))
	return NULL;
    
    srandom(seed);
    
    for (kbytes = 0; kbytes < len/1024; kbytes++)
    {
	unsigned i;
	for (i = 0; i < sizeof(buf)/sizeof(buf[0]); i++)
	    buf[i] = random();
	ret = write(fd, buf, sizeof(buf));
	if (ret < 0)
	    ret = 0;
	written += ret;
	if (ret < (int)sizeof(buf))
	    break;
	if (verbose && kbytes/1024 > 0 && !(kbytes%1024))
	    fprintf(stderr, "Random: %lld Mbytes\r", kbytes/1024);
    }
    
    // handle non-multiples of 1024
    if (len % 1024)
    {
	unsigned i;
	for (i = 0; i < sizeof(buf)/sizeof(buf[0]); i++)
	    buf[i] = random();
	ret = write(fd, buf, len % 1024);
	if (ret < 0)
	    ret = 0;
	written += ret;
    }
    
    if (kbytes/1024 > 0)
	fprintf(stderr, "Random: %lld Mbytes, done.\n", kbytes/1024);
    return Py_BuildValue("L", written);
}


static PyObject *random_sha(PyObject *self, PyObject *args)
{
    static int seeded = 0;
    uint32_t shabuf[20/4];
    int i;
    
    if (!seeded)
    {
	assert(sizeof(shabuf) == 20);
	srandom(time(NULL));
	seeded = 1;
    }
    
    if (!PyArg_ParseTuple(args, ""))
	return NULL;
    
    memset(shabuf, 0, sizeof(shabuf));
    for (i=0; i < 20/4; i++)
	shabuf[i] = random();
    return Py_BuildValue(rbuf_argf, shabuf, 20);
}


static int _open_noatime(const char *filename, int attrs)
{
    int attrs_noatime, fd;
    attrs |= O_RDONLY;
#ifdef O_NOFOLLOW
    attrs |= O_NOFOLLOW;
#endif
#ifdef O_LARGEFILE
    attrs |= O_LARGEFILE;
#endif
    attrs_noatime = attrs;
#ifdef O_NOATIME
    attrs_noatime |= O_NOATIME;
#endif
    fd = open(filename, attrs_noatime);
    if (fd < 0 && errno == EPERM)
    {
	// older Linux kernels would return EPERM if you used O_NOATIME
	// and weren't the file's owner.  This pointless restriction was
	// relaxed eventually, but we have to handle it anyway.
	// (VERY old kernels didn't recognized O_NOATIME, but they would
	// just harmlessly ignore it, so this branch won't trigger)
	fd = open(filename, attrs);
    }
    return fd;
}


static PyObject *open_noatime(PyObject *self, PyObject *args)
{
    char *filename = NULL;
    int fd;
    if (!PyArg_ParseTuple(args, cstr_argf, &filename))
	return NULL;
    fd = _open_noatime(filename, 0);
    if (fd < 0)
	return PyErr_SetFromErrnoWithFilename(PyExc_OSError, filename);
    return Py_BuildValue("i", fd);
}


static PyObject *fadvise_done(PyObject *self, PyObject *args)
{
    int fd = -1;
    long long llofs, lllen = 0;
    if (!PyArg_ParseTuple(args, "iLL", &fd, &llofs, &lllen))
	return NULL;
    off_t ofs, len;
    if (!INTEGRAL_ASSIGNMENT_FITS(&ofs, llofs))
        return PyErr_Format(PyExc_OverflowError,
                            "fadvise offset overflows off_t");
    if (!INTEGRAL_ASSIGNMENT_FITS(&len, lllen))
        return PyErr_Format(PyExc_OverflowError,
                            "fadvise length overflows off_t");
#ifdef POSIX_FADV_DONTNEED
    posix_fadvise(fd, ofs, len, POSIX_FADV_DONTNEED);
#endif    
    return Py_BuildValue("");
}


// Currently the Linux kernel and FUSE disagree over the type for
// FS_IOC_GETFLAGS and FS_IOC_SETFLAGS.  The kernel actually uses int,
// but FUSE chose long (matching the declaration in linux/fs.h).  So
// if you use int, and then traverse a FUSE filesystem, you may
// corrupt the stack.  But if you use long, then you may get invalid
// results on big-endian systems.
//
// For now, we just use long, and then disable Linux attrs entirely
// (with a warning) in helpers.py on systems that are affected.

#ifdef BUP_HAVE_FILE_ATTRS
static PyObject *bup_get_linux_file_attr(PyObject *self, PyObject *args)
{
    int rc;
    unsigned long attr;
    char *path;
    int fd;

    if (!PyArg_ParseTuple(args, cstr_argf, &path))
        return NULL;

    fd = _open_noatime(path, O_NONBLOCK);
    if (fd == -1)
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);

    attr = 0;  // Handle int/long mismatch (see above)
    rc = ioctl(fd, FS_IOC_GETFLAGS, &attr);
    if (rc == -1)
    {
        close(fd);
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
    }
    close(fd);
    assert(attr <= UINT_MAX);  // Kernel type is actually int
    return PyLong_FromUnsignedLong(attr);
}
#endif /* def BUP_HAVE_FILE_ATTRS */



#ifdef BUP_HAVE_FILE_ATTRS
static PyObject *bup_set_linux_file_attr(PyObject *self, PyObject *args)
{
    int rc;
    unsigned long orig_attr;
    unsigned int attr;
    char *path;
    PyObject *py_attr;
    int fd;

    if (!PyArg_ParseTuple(args, cstr_argf "O", &path, &py_attr))
        return NULL;

    if (!bup_uint_from_py(&attr, py_attr, "attr"))
        return NULL;

    fd = open(path, O_RDONLY | O_NONBLOCK | O_LARGEFILE | O_NOFOLLOW);
    if (fd == -1)
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);

    // Restrict attr to modifiable flags acdeijstuADST -- see
    // chattr(1) and the e2fsprogs source.  Letter to flag mapping is
    // in pf.c flags_array[].
    attr &= FS_APPEND_FL | FS_COMPR_FL | FS_NODUMP_FL | FS_EXTENT_FL
    | FS_IMMUTABLE_FL | FS_JOURNAL_DATA_FL | FS_SECRM_FL | FS_NOTAIL_FL
    | FS_UNRM_FL | FS_NOATIME_FL | FS_DIRSYNC_FL | FS_SYNC_FL
    | FS_TOPDIR_FL | FS_NOCOW_FL;

    // The extents flag can't be removed, so don't (see chattr(1) and chattr.c).
    orig_attr = 0; // Handle int/long mismatch (see above)
    rc = ioctl(fd, FS_IOC_GETFLAGS, &orig_attr);
    if (rc == -1)
    {
        close(fd);
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
    }
    assert(orig_attr <= UINT_MAX);  // Kernel type is actually int
    attr |= ((unsigned int) orig_attr) & FS_EXTENT_FL;

    rc = ioctl(fd, FS_IOC_SETFLAGS, &attr);
    if (rc == -1)
    {
        close(fd);
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
    }

    close(fd);
    return Py_BuildValue("O", Py_None);
}
#endif /* def BUP_HAVE_FILE_ATTRS */


#ifndef HAVE_UTIMENSAT
#ifndef HAVE_UTIMES
#error "cannot find utimensat or utimes()"
#endif
#ifndef HAVE_LUTIMES
#error "cannot find utimensat or lutimes()"
#endif
#endif

#define ASSIGN_PYLONG_TO_INTEGRAL(dest, pylong, overflow) \
    ({                                                     \
        int result = 0;                                                 \
        *(overflow) = 0;                                                \
        const long long lltmp = PyLong_AsLongLong(pylong);              \
        if (lltmp == -1 && PyErr_Occurred())                            \
        {                                                               \
            if (PyErr_ExceptionMatches(PyExc_OverflowError))            \
            {                                                           \
                const unsigned long long ulltmp = PyLong_AsUnsignedLongLong(pylong); \
                if (ulltmp == (unsigned long long) -1 && PyErr_Occurred()) \
                {                                                       \
                    if (PyErr_ExceptionMatches(PyExc_OverflowError))    \
                    {                                                   \
                        PyErr_Clear();                                  \
                        *(overflow) = 1;                                \
                    }                                                   \
                }                                                       \
                if (INTEGRAL_ASSIGNMENT_FITS((dest), ulltmp))           \
                    result = 1;                                         \
                else                                                    \
                    *(overflow) = 1;                                    \
            }                                                           \
        }                                                               \
        else                                                            \
        {                                                               \
            if (INTEGRAL_ASSIGNMENT_FITS((dest), lltmp))                \
                result = 1;                                             \
            else                                                        \
                *(overflow) = 1;                                        \
        }                                                               \
        result;                                                         \
        })


#ifdef HAVE_UTIMENSAT

static PyObject *bup_utimensat(PyObject *self, PyObject *args)
{
    int rc;
    int fd, flag;
    char *path;
    PyObject *access_py, *modification_py;
    struct timespec ts[2];

    if (!PyArg_ParseTuple(args, "i" cstr_argf "((Ol)(Ol))i",
                          &fd,
                          &path,
                          &access_py, &(ts[0].tv_nsec),
                          &modification_py, &(ts[1].tv_nsec),
                          &flag))
        return NULL;

    int overflow;
    if (!ASSIGN_PYLONG_TO_INTEGRAL(&(ts[0].tv_sec), access_py, &overflow))
    {
        if (overflow)
            PyErr_SetString(PyExc_ValueError,
                            "unable to convert access time seconds for utimensat");
        return NULL;
    }
    if (!ASSIGN_PYLONG_TO_INTEGRAL(&(ts[1].tv_sec), modification_py, &overflow))
    {
        if (overflow)
            PyErr_SetString(PyExc_ValueError,
                            "unable to convert modification time seconds for utimensat");
        return NULL;
    }
    rc = utimensat(fd, path, ts, flag);
    if (rc != 0)
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);

    return Py_BuildValue("O", Py_None);
}

#endif /* def HAVE_UTIMENSAT */


#if defined(HAVE_UTIMES) || defined(HAVE_LUTIMES)

static int bup_parse_xutimes_args(char **path,
                                  struct timeval tv[2],
                                  PyObject *args)
{
    PyObject *access_py, *modification_py;
    long long access_us, modification_us; // POSIX guarantees tv_usec is signed.

    if (!PyArg_ParseTuple(args, cstr_argf "((OL)(OL))",
                          path,
                          &access_py, &access_us,
                          &modification_py, &modification_us))
        return 0;

    int overflow;
    if (!ASSIGN_PYLONG_TO_INTEGRAL(&(tv[0].tv_sec), access_py, &overflow))
    {
        if (overflow)
            PyErr_SetString(PyExc_ValueError, "unable to convert access time seconds to timeval");
        return 0;
    }
    if (!INTEGRAL_ASSIGNMENT_FITS(&(tv[0].tv_usec), access_us))
    {
        PyErr_SetString(PyExc_ValueError, "unable to convert access time nanoseconds to timeval");
        return 0;
    }
    if (!ASSIGN_PYLONG_TO_INTEGRAL(&(tv[1].tv_sec), modification_py, &overflow))
    {
        if (overflow)
            PyErr_SetString(PyExc_ValueError, "unable to convert modification time seconds to timeval");
        return 0;
    }
    if (!INTEGRAL_ASSIGNMENT_FITS(&(tv[1].tv_usec), modification_us))
    {
        PyErr_SetString(PyExc_ValueError, "unable to convert modification time nanoseconds to timeval");
        return 0;
    }
    return 1;
}

#endif /* defined(HAVE_UTIMES) || defined(HAVE_LUTIMES) */


#ifdef HAVE_UTIMES
static PyObject *bup_utimes(PyObject *self, PyObject *args)
{
    char *path;
    struct timeval tv[2];
    if (!bup_parse_xutimes_args(&path, tv, args))
        return NULL;
    int rc = utimes(path, tv);
    if (rc != 0)
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
    return Py_BuildValue("O", Py_None);
}
#endif /* def HAVE_UTIMES */


#ifdef HAVE_LUTIMES
static PyObject *bup_lutimes(PyObject *self, PyObject *args)
{
    char *path;
    struct timeval tv[2];
    if (!bup_parse_xutimes_args(&path, tv, args))
        return NULL;
    int rc = lutimes(path, tv);
    if (rc != 0)
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);

    return Py_BuildValue("O", Py_None);
}
#endif /* def HAVE_LUTIMES */


#ifdef HAVE_STAT_ST_ATIM
# define BUP_STAT_ATIME_NS(st) (st)->st_atim.tv_nsec
# define BUP_STAT_MTIME_NS(st) (st)->st_mtim.tv_nsec
# define BUP_STAT_CTIME_NS(st) (st)->st_ctim.tv_nsec
#elif defined HAVE_STAT_ST_ATIMENSEC
# define BUP_STAT_ATIME_NS(st) (st)->st_atimespec.tv_nsec
# define BUP_STAT_MTIME_NS(st) (st)->st_mtimespec.tv_nsec
# define BUP_STAT_CTIME_NS(st) (st)->st_ctimespec.tv_nsec
#else
# define BUP_STAT_ATIME_NS(st) 0
# define BUP_STAT_MTIME_NS(st) 0
# define BUP_STAT_CTIME_NS(st) 0
#endif


#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wtautological-compare" // For INTEGER_TO_PY().

static PyObject *stat_struct_to_py(const struct stat *st,
                                   const char *filename,
                                   int fd)
{
    // We can check the known (via POSIX) signed and unsigned types at
    // compile time, but not (easily) the unspecified types, so handle
    // those via INTEGER_TO_PY().  Assumes ns values will fit in a
    // long.
    return Py_BuildValue("NKNNNNNL(Nl)(Nl)(Nl)",
                         INTEGER_TO_PY(st->st_mode),
                         (unsigned PY_LONG_LONG) st->st_ino,
                         INTEGER_TO_PY(st->st_dev),
                         INTEGER_TO_PY(st->st_nlink),
                         INTEGER_TO_PY(st->st_uid),
                         INTEGER_TO_PY(st->st_gid),
                         INTEGER_TO_PY(st->st_rdev),
                         (PY_LONG_LONG) st->st_size,
                         INTEGER_TO_PY(st->st_atime),
                         (long) BUP_STAT_ATIME_NS(st),
                         INTEGER_TO_PY(st->st_mtime),
                         (long) BUP_STAT_MTIME_NS(st),
                         INTEGER_TO_PY(st->st_ctime),
                         (long) BUP_STAT_CTIME_NS(st));
}

#pragma clang diagnostic pop  // ignored "-Wtautological-compare"

static PyObject *bup_stat(PyObject *self, PyObject *args)
{
    int rc;
    char *filename;

    if (!PyArg_ParseTuple(args, cstr_argf, &filename))
        return NULL;

    struct stat st;
    rc = stat(filename, &st);
    if (rc != 0)
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, filename);
    return stat_struct_to_py(&st, filename, 0);
}


static PyObject *bup_lstat(PyObject *self, PyObject *args)
{
    int rc;
    char *filename;

    if (!PyArg_ParseTuple(args, cstr_argf, &filename))
        return NULL;

    struct stat st;
    rc = lstat(filename, &st);
    if (rc != 0)
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, filename);
    return stat_struct_to_py(&st, filename, 0);
}


static PyObject *bup_fstat(PyObject *self, PyObject *args)
{
    int rc, fd;

    if (!PyArg_ParseTuple(args, "i", &fd))
        return NULL;

    struct stat st;
    rc = fstat(fd, &st);
    if (rc != 0)
        return PyErr_SetFromErrno(PyExc_OSError);
    return stat_struct_to_py(&st, NULL, fd);
}


#ifdef HAVE_TM_TM_GMTOFF
static PyObject *bup_localtime(PyObject *self, PyObject *args)
{
    long long lltime;
    time_t ttime;
    if (!PyArg_ParseTuple(args, "L", &lltime))
	return NULL;
    if (!INTEGRAL_ASSIGNMENT_FITS(&ttime, lltime))
        return PyErr_Format(PyExc_OverflowError, "time value too large");

    struct tm tm;
    tzset();
    if(localtime_r(&ttime, &tm) == NULL)
        return PyErr_SetFromErrno(PyExc_OSError);

    // Match the Python struct_time values.
    return Py_BuildValue("[i,i,i,i,i,i,i,i,i,i,s]",
                         1900 + tm.tm_year, tm.tm_mon + 1, tm.tm_mday,
                         tm.tm_hour, tm.tm_min, tm.tm_sec,
                         tm.tm_wday, tm.tm_yday + 1,
                         tm.tm_isdst, tm.tm_gmtoff, tm.tm_zone);
}
#endif /* def HAVE_TM_TM_GMTOFF */


#ifdef BUP_MINCORE_BUF_TYPE
static PyObject *bup_mincore(PyObject *self, PyObject *args)
{
    Py_buffer src, dest;
    PyObject *py_src_n, *py_src_off, *py_dest_off;

    if (!PyArg_ParseTuple(args, cstr_argf "*OOw*O",
                          &src, &py_src_n, &py_src_off,
                          &dest, &py_dest_off))
	return NULL;

    PyObject *result = NULL;

    unsigned long long src_n, src_off, dest_off;
    if (!(bup_ullong_from_py(&src_n, py_src_n, "src_n")
          && bup_ullong_from_py(&src_off, py_src_off, "src_off")
          && bup_ullong_from_py(&dest_off, py_dest_off, "dest_off")))
        goto clean_and_return;

    unsigned long long src_region_end;
    if (!uadd(&src_region_end, src_off, src_n)) {
        result = PyErr_Format(PyExc_OverflowError, "(src_off + src_n) too large");
        goto clean_and_return;
    }
    assert(src.len >= 0);
    if (src_region_end > (unsigned long long) src.len) {
        result = PyErr_Format(PyExc_OverflowError, "region runs off end of src");
        goto clean_and_return;
    }

    unsigned long long dest_size;
    if (!INTEGRAL_ASSIGNMENT_FITS(&dest_size, dest.len)) {
        result = PyErr_Format(PyExc_OverflowError, "invalid dest size");
        goto clean_and_return;
    }
    if (dest_off > dest_size) {
        result = PyErr_Format(PyExc_OverflowError, "region runs off end of dest");
        goto clean_and_return;
    }

    size_t length;
    if (!INTEGRAL_ASSIGNMENT_FITS(&length, src_n)) {
        result = PyErr_Format(PyExc_OverflowError, "src_n overflows size_t");
        goto clean_and_return;
    }
    int rc = mincore((void *)(src.buf + src_off), src_n,
                     (BUP_MINCORE_BUF_TYPE *) (dest.buf + dest_off));
    if (rc != 0) {
        result = PyErr_SetFromErrno(PyExc_OSError);
        goto clean_and_return;
    }
    result = Py_BuildValue("O", Py_None);

 clean_and_return:
    PyBuffer_Release(&src);
    PyBuffer_Release(&dest);
    return result;
}
#endif /* def BUP_MINCORE_BUF_TYPE */


static PyObject *tuple_from_cstrs(char **cstrs)
{
    // Assumes list is null terminated
    size_t n = 0;
    while(cstrs[n] != NULL)
        n++;

    Py_ssize_t sn;
    if (!INTEGRAL_ASSIGNMENT_FITS(&sn, n))
        return PyErr_Format(PyExc_OverflowError, "string array too large");

    PyObject *result = PyTuple_New(sn);
    Py_ssize_t i = 0;
    for (i = 0; i < sn; i++)
    {
        PyObject *gname = Py_BuildValue(cstr_argf, cstrs[i]);
        if (gname == NULL)
        {
            Py_DECREF(result);
            return NULL;
        }
        PyTuple_SET_ITEM(result, i, gname);
    }
    return result;
}

static long getpw_buf_size;

static PyObject *pwd_struct_to_py(const struct passwd *pwd, int rc)
{
    // We can check the known (via POSIX) signed and unsigned types at
    // compile time, but not (easily) the unspecified types, so handle
    // those via INTEGER_TO_PY().
    if (pwd != NULL)
        return Py_BuildValue(cstr_argf cstr_argf "OO"
                             cstr_argf cstr_argf cstr_argf,
                             pwd->pw_name,
                             pwd->pw_passwd,
                             INTEGER_TO_PY(pwd->pw_uid),
                             INTEGER_TO_PY(pwd->pw_gid),
                             pwd->pw_gecos,
                             pwd->pw_dir,
                             pwd->pw_shell);
    if (rc == 0)
        return Py_BuildValue("O", Py_None);
    if (rc == EIO || rc == EMFILE || rc == ENFILE)
        return PyErr_SetFromErrno(PyExc_IOError);
    if (rc < 0)
        return PyErr_SetFromErrno(PyExc_OSError);
    assert(0);
}

static PyObject *bup_getpwuid(PyObject *self, PyObject *args)
{
    unsigned long uid;
    if (!PyArg_ParseTuple(args, "k", &uid))
	return NULL;

    struct passwd pwd, *result_pwd;
    char *buf = PyMem_Malloc(getpw_buf_size);
    if (buf == NULL)
        return NULL;

    int rc = getpwuid_r(uid, &pwd, buf, getpw_buf_size, &result_pwd);
    PyObject *result = pwd_struct_to_py(result_pwd, rc);
    PyMem_Free(buf);
    return result;
}

static PyObject *bup_getpwnam(PyObject *self, PyObject *args)
{
    PyObject *py_name;
    if (!PyArg_ParseTuple(args, "S", &py_name))
	return NULL;

    struct passwd pwd, *result_pwd;
    char *buf = PyMem_Malloc(getpw_buf_size);
    if (buf == NULL)
        return NULL;

    char *name = PyBytes_AS_STRING(py_name);
    int rc = getpwnam_r(name, &pwd, buf, getpw_buf_size, &result_pwd);
    PyObject *result = pwd_struct_to_py(result_pwd, rc);
    PyMem_Free(buf);
    return result;
}

static long getgr_buf_size;

static PyObject *grp_struct_to_py(const struct group *grp, int rc)
{
    // We can check the known (via POSIX) signed and unsigned types at
    // compile time, but not (easily) the unspecified types, so handle
    // those via INTEGER_TO_PY().
    if (grp != NULL) {
        PyObject *members = tuple_from_cstrs(grp->gr_mem);
        if (members == NULL)
            return NULL;
        return Py_BuildValue(cstr_argf cstr_argf "OO",
                             grp->gr_name,
                             grp->gr_passwd,
                             INTEGER_TO_PY(grp->gr_gid),
                             members);
    }
    if (rc == 0)
        return Py_BuildValue("O", Py_None);
    if (rc == EIO || rc == EMFILE || rc == ENFILE)
        return PyErr_SetFromErrno(PyExc_IOError);
    if (rc < 0)
        return PyErr_SetFromErrno(PyExc_OSError);
    assert (0);
}

static PyObject *bup_getgrgid(PyObject *self, PyObject *args)
{
    unsigned long gid;
    if (!PyArg_ParseTuple(args, "k", &gid))
	return NULL;

    struct group grp, *result_grp;
    char *buf = PyMem_Malloc(getgr_buf_size);
    if (buf == NULL)
        return NULL;

    int rc = getgrgid_r(gid, &grp, buf, getgr_buf_size, &result_grp);
    PyObject *result = grp_struct_to_py(result_grp, rc);
    PyMem_Free(buf);
    return result;
}

static PyObject *bup_getgrnam(PyObject *self, PyObject *args)
{
    PyObject *py_name;
    if (!PyArg_ParseTuple(args, "S", &py_name))
	return NULL;

    struct group grp, *result_grp;
    char *buf = PyMem_Malloc(getgr_buf_size);
    if (buf == NULL)
        return NULL;

    char *name = PyBytes_AS_STRING(py_name);
    int rc = getgrnam_r(name, &grp, buf, getgr_buf_size, &result_grp);
    PyObject *result = grp_struct_to_py(result_grp, rc);
    PyMem_Free(buf);
    return result;
}

static PyMethodDef helper_methods[] = {
    { "write_sparsely", bup_write_sparsely, METH_VARARGS,
      "Write buf excepting zeros at the end. Return trailing zero count." },
    { "selftest", selftest, METH_VARARGS,
	"Check that the rolling checksum rolls correctly (for unit tests)." },
    { "blobbits", blobbits, METH_VARARGS,
	"Return the number of bits in the rolling checksum." },
    { "splitbuf", splitbuf, METH_VARARGS,
	"Split a list of strings based on a rolling checksum." },
    { "bitmatch", bitmatch, METH_VARARGS,
	"Count the number of matching prefix bits between two strings." },
    { "firstword", firstword, METH_VARARGS,
        "Return an int corresponding to the first 32 bits of buf." },
    { "bloom_contains", bloom_contains, METH_VARARGS,
	"Check if a bloom filter of 2^nbits bytes contains an object" },
    { "bloom_add", bloom_add, METH_VARARGS,
	"Add an object to a bloom filter of 2^nbits bytes" },
    { "extract_bits", extract_bits, METH_VARARGS,
	"Take the first 'nbits' bits from 'buf' and return them as an int." },
    { "merge_into", merge_into, METH_VARARGS,
	"Merges a bunch of idx and midx files into a single midx." },
    { "write_idx", write_idx, METH_VARARGS,
	"Write a PackIdxV2 file from an idx list of lists of tuples" },
    { "write_random", write_random, METH_VARARGS,
	"Write random bytes to the given file descriptor" },
    { "random_sha", random_sha, METH_VARARGS,
        "Return a random 20-byte string" },
    { "open_noatime", open_noatime, METH_VARARGS,
	"open() the given filename for read with O_NOATIME if possible" },
    { "fadvise_done", fadvise_done, METH_VARARGS,
	"Inform the kernel that we're finished with earlier parts of a file" },
#ifdef BUP_HAVE_FILE_ATTRS
    { "get_linux_file_attr", bup_get_linux_file_attr, METH_VARARGS,
      "Return the Linux attributes for the given file." },
#endif
#ifdef BUP_HAVE_FILE_ATTRS
    { "set_linux_file_attr", bup_set_linux_file_attr, METH_VARARGS,
      "Set the Linux attributes for the given file." },
#endif
#ifdef HAVE_UTIMENSAT
    { "bup_utimensat", bup_utimensat, METH_VARARGS,
      "Change path timestamps with nanosecond precision (POSIX)." },
#endif
#ifdef HAVE_UTIMES
    { "bup_utimes", bup_utimes, METH_VARARGS,
      "Change path timestamps with microsecond precision." },
#endif
#ifdef HAVE_LUTIMES
    { "bup_lutimes", bup_lutimes, METH_VARARGS,
      "Change path timestamps with microsecond precision;"
      " don't follow symlinks." },
#endif
    { "stat", bup_stat, METH_VARARGS,
      "Extended version of stat." },
    { "lstat", bup_lstat, METH_VARARGS,
      "Extended version of lstat." },
    { "fstat", bup_fstat, METH_VARARGS,
      "Extended version of fstat." },
#ifdef HAVE_TM_TM_GMTOFF
    { "localtime", bup_localtime, METH_VARARGS,
      "Return struct_time elements plus the timezone offset and name." },
#endif
    { "bytescmp", bup_bytescmp, METH_VARARGS,
      "Return a negative value if x < y, zero if equal, positive otherwise."},
    { "cat_bytes", bup_cat_bytes, METH_VARARGS,
      "For (x_bytes, x_ofs, x_n, y_bytes, y_ofs, y_n) arguments, return their concatenation."},
#ifdef BUP_MINCORE_BUF_TYPE
    { "mincore", bup_mincore, METH_VARARGS,
      "For mincore(src, src_n, src_off, dest, dest_off)"
      " call the system mincore(src + src_off, src_n, &dest[dest_off])." },
#endif
    { "getpwuid", bup_getpwuid, METH_VARARGS,
      "Return the password database entry for the given numeric user id,"
      " as a tuple with all C strings as bytes(), or None if the user does"
      " not exist." },
    { "getpwnam", bup_getpwnam, METH_VARARGS,
      "Return the password database entry for the given user name,"
      " as a tuple with all C strings as bytes(), or None if the user does"
      " not exist." },
    { "getgrgid", bup_getgrgid, METH_VARARGS,
      "Return the group database entry for the given numeric group id,"
      " as a tuple with all C strings as bytes(), or None if the group does"
      " not exist." },
    { "getgrnam", bup_getgrnam, METH_VARARGS,
      "Return the group database entry for the given group name,"
      " as a tuple with all C strings as bytes(), or None if the group does"
      " not exist." },
    { NULL, NULL, 0, NULL },  // sentinel
};

static void test_integral_assignment_fits(void)
{
    assert(sizeof(signed short) == sizeof(unsigned short));
    assert(sizeof(signed short) < sizeof(signed long long));
    assert(sizeof(signed short) < sizeof(unsigned long long));
    assert(sizeof(unsigned short) < sizeof(signed long long));
    assert(sizeof(unsigned short) < sizeof(unsigned long long));
    assert(sizeof(Py_ssize_t) <= sizeof(size_t));
    {
        signed short ss, ssmin = SHRT_MIN, ssmax = SHRT_MAX;
        unsigned short us, usmax = USHRT_MAX;
        signed long long sllmin = LLONG_MIN, sllmax = LLONG_MAX;
        unsigned long long ullmax = ULLONG_MAX;

        assert(INTEGRAL_ASSIGNMENT_FITS(&ss, ssmax));
        assert(INTEGRAL_ASSIGNMENT_FITS(&ss, ssmin));
        assert(!INTEGRAL_ASSIGNMENT_FITS(&ss, usmax));
        assert(!INTEGRAL_ASSIGNMENT_FITS(&ss, sllmin));
        assert(!INTEGRAL_ASSIGNMENT_FITS(&ss, sllmax));
        assert(!INTEGRAL_ASSIGNMENT_FITS(&ss, ullmax));

        assert(INTEGRAL_ASSIGNMENT_FITS(&us, usmax));
        assert(!INTEGRAL_ASSIGNMENT_FITS(&us, ssmin));
        assert(!INTEGRAL_ASSIGNMENT_FITS(&us, sllmin));
        assert(!INTEGRAL_ASSIGNMENT_FITS(&us, sllmax));
        assert(!INTEGRAL_ASSIGNMENT_FITS(&us, ullmax));
    }
}

static int setup_module(PyObject *m)
{
    // FIXME: migrate these tests to configure, or at least don't
    // possibly crash the whole application.  Check against the type
    // we're going to use when passing to python.  Other stat types
    // are tested at runtime.
    assert(sizeof(ino_t) <= sizeof(unsigned PY_LONG_LONG));
    assert(sizeof(off_t) <= sizeof(PY_LONG_LONG));
    assert(sizeof(blksize_t) <= sizeof(PY_LONG_LONG));
    assert(sizeof(blkcnt_t) <= sizeof(PY_LONG_LONG));
    // Just be sure (relevant when passing timestamps back to Python above).
    assert(sizeof(PY_LONG_LONG) <= sizeof(long long));
    assert(sizeof(unsigned PY_LONG_LONG) <= sizeof(unsigned long long));

    test_integral_assignment_fits();

    // Originally required by append_sparse_region()
    {
        off_t probe;
        if (!INTEGRAL_ASSIGNMENT_FITS(&probe, INT_MAX))
        {
            fprintf(stderr, "off_t can't hold INT_MAX; please report.\n");
            exit(1);
        }
    }

    char *e;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wtautological-compare" // For INTEGER_TO_PY().
    {
        PyObject *value;
        value = INTEGER_TO_PY(INT_MAX);
        PyObject_SetAttrString(m, "INT_MAX", value);
        Py_DECREF(value);
        value = INTEGER_TO_PY(UINT_MAX);
        PyObject_SetAttrString(m, "UINT_MAX", value);
        Py_DECREF(value);
    }
#ifdef HAVE_UTIMENSAT
    {
        PyObject *value;
        value = INTEGER_TO_PY(AT_FDCWD);
        PyObject_SetAttrString(m, "AT_FDCWD", value);
        Py_DECREF(value);
        value = INTEGER_TO_PY(AT_SYMLINK_NOFOLLOW);
        PyObject_SetAttrString(m, "AT_SYMLINK_NOFOLLOW", value);
        Py_DECREF(value);
        value = INTEGER_TO_PY(UTIME_NOW);
        PyObject_SetAttrString(m, "UTIME_NOW", value);
        Py_DECREF(value);
    }
#endif
#ifdef BUP_HAVE_MINCORE_INCORE
    {
        PyObject *value;
        value = INTEGER_TO_PY(MINCORE_INCORE);
        PyObject_SetAttrString(m, "MINCORE_INCORE", value);
        Py_DECREF(value);
    }
#endif
#pragma clang diagnostic pop  // ignored "-Wtautological-compare"

    getpw_buf_size = sysconf(_SC_GETPW_R_SIZE_MAX);
    if (getpw_buf_size == -1)
        getpw_buf_size = 16384;

    getgr_buf_size = sysconf(_SC_GETGR_R_SIZE_MAX);
    if (getgr_buf_size == -1)
        getgr_buf_size = 16384;

    e = getenv("BUP_FORCE_TTY");
    get_state(m)->istty2 = isatty(2) || (atoi(e ? e : "0") & 2);
    unpythonize_argv();
    return 1;
}


#if PY_MAJOR_VERSION < 3

PyMODINIT_FUNC init_helpers(void)
{
    PyObject *m = Py_InitModule("_helpers", helper_methods);
    if (m == NULL)
        return;

    if (!setup_module(m))
    {
        Py_DECREF(m);
        return;
    }
}

# else // PY_MAJOR_VERSION >= 3

static struct PyModuleDef helpers_def = {
    PyModuleDef_HEAD_INIT,
    "_helpers",
    NULL,
    sizeof(state_t),
    helper_methods,
    NULL,
    NULL, // helpers_traverse,
    NULL, // helpers_clear,
    NULL
};

PyMODINIT_FUNC PyInit__helpers(void)
{
    PyObject *module = PyModule_Create(&helpers_def);
    if (module == NULL)
        return NULL;
    if (!setup_module(module))
    {
        Py_DECREF(module);
        return NULL;
    }
    return module;
}

#endif // PY_MAJOR_VERSION >= 3
