#define _LARGEFILE64_SOURCE 1
#define PY_SSIZE_T_CLEAN 1
#undef NDEBUG
#include "../../config/config.h"

// According to Python, its header has to go first:
//   http://docs.python.org/2/c-api/intro.html#include-files
#include <Python.h>

#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <arpa/inet.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <sys/mman.h>

#ifdef HAVE_SYS_TYPES_H
#include <sys/types.h>
#endif
#ifdef HAVE_SYS_STAT_H
#include <sys/stat.h>
#endif
#ifdef HAVE_UNISTD_H
#include <unistd.h>
#endif

#ifdef HAVE_LINUX_FS_H
#include <linux/fs.h>
#endif
#ifdef HAVE_SYS_IOCTL_H
#include <sys/ioctl.h>
#endif

#include "bupsplit.h"

#if defined(FS_IOC_GETFLAGS) && defined(FS_IOC_SETFLAGS)
#define BUP_HAVE_FILE_ATTRS 1
#endif

#ifndef FS_NOCOW_FL
// Of course, this assumes it's a bitfield value.
#define FS_NOCOW_FL 0
#endif

static int istty2 = 0;

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
    unsigned char *buf = NULL;
    Py_ssize_t len = 0;
    int out = 0, bits = -1;

    if (!PyArg_ParseTuple(args, "t#", &buf, &len))
	return NULL;
    assert(len <= INT_MAX);
    out = bupsplit_find_ofs(buf, len, &bits);
    if (out) assert(bits >= BUP_BLOBBITS);
    return Py_BuildValue("ii", out, bits);
}


static PyObject *bitmatch(PyObject *self, PyObject *args)
{
    unsigned char *buf1 = NULL, *buf2 = NULL;
    Py_ssize_t len1 = 0, len2 = 0;
    Py_ssize_t byte;
    int bit;

    if (!PyArg_ParseTuple(args, "t#t#", &buf1, &len1, &buf2, &len2))
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

    if (!PyArg_ParseTuple(args, "t#", &buf, &len))
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
    unsigned char *sha = NULL, *bloom = NULL;
    unsigned char *end;
    Py_ssize_t len = 0, blen = 0;
    int nbits = 0, k = 0;

    if (!PyArg_ParseTuple(args, "w#s#ii", &bloom, &blen, &sha, &len, &nbits, &k))
	return NULL;

    if (blen < 16+(1<<nbits) || len % 20 != 0)
	return NULL;

    if (k == 5)
    {
	if (nbits > 29)
	    return NULL;
	for (end = sha + len; sha < end; sha += 20/k)
	    bloom_set_bit5(bloom, sha, nbits);
    }
    else if (k == 4)
    {
	if (nbits > 37)
	    return NULL;
	for (end = sha + len; sha < end; sha += 20/k)
	    bloom_set_bit4(bloom, sha, nbits);
    }
    else
	return NULL;


    return Py_BuildValue("n", len/20);
}

static PyObject *bloom_contains(PyObject *self, PyObject *args)
{
    unsigned char *sha = NULL, *bloom = NULL;
    Py_ssize_t len = 0, blen = 0;
    int nbits = 0, k = 0;
    unsigned char *end;
    int steps;

    if (!PyArg_ParseTuple(args, "t#s#ii", &bloom, &blen, &sha, &len, &nbits, &k))
	return NULL;

    if (len != 20)
	return NULL;

    if (k == 5)
    {
	if (nbits > 29)
	    return NULL;
	for (steps = 1, end = sha + 20; sha < end; sha += 20/k, steps++)
	    if (!bloom_get_bit5(bloom, sha, nbits))
		return Py_BuildValue("Oi", Py_None, steps);
    }
    else if (k == 4)
    {
	if (nbits > 37)
	    return NULL;
	for (steps = 1, end = sha + 20; sha < end; sha += 20/k, steps++)
	    if (!bloom_get_bit4(bloom, sha, nbits))
		return Py_BuildValue("Oi", Py_None, steps);
    }
    else
	return NULL;

    return Py_BuildValue("ii", 1, k);
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

    if (!PyArg_ParseTuple(args, "t#i", &buf, &len, &nbits))
	return NULL;
    
    if (len < 4)
	return NULL;
    
    return PyLong_FromUnsignedLong(_extract_bits(buf, nbits));
}


struct sha {
    unsigned char bytes[20];
};


struct idx {
    unsigned char *map;
    struct sha *cur;
    struct sha *end;
    uint32_t *cur_name;
    Py_ssize_t bytes;
    int name_base;
};


static int _cmp_sha(const struct sha *sha1, const struct sha *sha2)
{
    int i;
    for (i = 0; i < sizeof(struct sha); i++)
	if (sha1->bytes[i] != sha2->bytes[i])
	    return sha1->bytes[i] - sha2->bytes[i];
    return 0;
}


static void _fix_idx_order(struct idx **idxs, int *last_i)
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
    PyObject *ilist = NULL;
    unsigned char *fmap = NULL;
    struct sha *sha_ptr, *sha_start = NULL;
    uint32_t *table_ptr, *name_ptr, *name_start;
    struct idx **idxs = NULL;
    Py_ssize_t flen = 0;
    int bits = 0, i;
    unsigned int total;
    uint32_t count, prefix;
    int num_i;
    int last_i;

    if (!PyArg_ParseTuple(args, "w#iIO", &fmap, &flen, &bits, &total, &ilist))
	return NULL;

    num_i = PyList_Size(ilist);
    idxs = (struct idx **)PyMem_Malloc(num_i * sizeof(struct idx *));

    for (i = 0; i < num_i; i++)
    {
	long len, sha_ofs, name_map_ofs;
	idxs[i] = (struct idx *)PyMem_Malloc(sizeof(struct idx));
	PyObject *itup = PyList_GetItem(ilist, i);
	if (!PyArg_ParseTuple(itup, "t#llli", &idxs[i]->map, &idxs[i]->bytes,
		    &len, &sha_ofs, &name_map_ofs, &idxs[i]->name_base))
	    return NULL;
	idxs[i]->cur = (struct sha *)&idxs[i]->map[sha_ofs];
	idxs[i]->end = &idxs[i]->cur[len];
	if (name_map_ofs)
	    idxs[i]->cur_name = (uint32_t *)&idxs[i]->map[name_map_ofs];
	else
	    idxs[i]->cur_name = NULL;
    }
    table_ptr = (uint32_t *)&fmap[MIDX4_HEADERLEN];
    sha_start = sha_ptr = (struct sha *)&table_ptr[1<<bits];
    name_start = name_ptr = (uint32_t *)&sha_ptr[total];

    last_i = num_i-1;
    count = 0;
    prefix = 0;
    while (last_i >= 0)
    {
	struct idx *idx;
	uint32_t new_prefix;
	if (count % 102424 == 0 && istty2)
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
    while (prefix < (1<<bits))
	table_ptr[prefix++] = htonl(count);
    assert(count == total);
    assert(prefix == (1<<bits));
    assert(sha_ptr == sha_start+count);
    assert(name_ptr == name_start+count);

    PyMem_Free(idxs);
    return PyLong_FromUnsignedLong(count);
}

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

#define FAN_ENTRIES 256

static PyObject *write_idx(PyObject *self, PyObject *args)
{
    char *filename = NULL;
    PyObject *idx = NULL;
    PyObject *part;
    unsigned char *fmap = NULL;
    Py_ssize_t flen = 0;
    unsigned int total = 0;
    uint32_t count;
    int i, j, ofs64_count;
    uint32_t *fan_ptr, *crc_ptr, *ofs_ptr;
    uint64_t *ofs64_ptr;
    struct sha *sha_ptr;

    if (!PyArg_ParseTuple(args, "sw#OI", &filename, &fmap, &flen, &idx, &total))
	return NULL;

    if (PyList_Size (idx) != FAN_ENTRIES) // Check for list of the right length.
        return PyErr_Format (PyExc_TypeError, "idx must contain %d entries",
                             FAN_ENTRIES);

    const char idx_header[] = "\377tOc\0\0\0\002";
    memcpy (fmap, idx_header, sizeof(idx_header) - 1);

    fan_ptr = (uint32_t *)&fmap[sizeof(idx_header) - 1];
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
	    unsigned int crc = 0;
            unsigned PY_LONG_LONG ofs_py = 0;
	    uint64_t ofs;
	    if (!PyArg_ParseTuple(PyList_GET_ITEM(part, j), "t#IK",
				  &sha, &sha_len, &crc, &ofs_py))
		return NULL;
            assert(crc <= UINT32_MAX);
            assert(ofs_py <= UINT64_MAX);
	    ofs = ofs_py;
	    if (sha_len != sizeof(struct sha))
		return NULL;
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

    int rc = msync(fmap, flen, MS_ASYNC);
    if (rc != 0)
	return PyErr_SetFromErrnoWithFilename(PyExc_IOError, filename);

    return PyLong_FromUnsignedLong(count);
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
    return Py_BuildValue("s#", shabuf, 20);
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
    if (!PyArg_ParseTuple(args, "s", &filename))
	return NULL;
    fd = _open_noatime(filename, 0);
    if (fd < 0)
	return PyErr_SetFromErrnoWithFilename(PyExc_OSError, filename);
    return Py_BuildValue("i", fd);
}


static PyObject *fadvise_done(PyObject *self, PyObject *args)
{
    int fd = -1;
    long long ofs = 0;
    if (!PyArg_ParseTuple(args, "iL", &fd, &ofs))
	return NULL;
#ifdef POSIX_FADV_DONTNEED
    posix_fadvise(fd, 0, ofs, POSIX_FADV_DONTNEED);
#endif    
    return Py_BuildValue("");
}


#ifdef BUP_HAVE_FILE_ATTRS
static PyObject *bup_get_linux_file_attr(PyObject *self, PyObject *args)
{
    int rc;
    unsigned int attr;
    char *path;
    int fd;

    if (!PyArg_ParseTuple(args, "s", &path))
        return NULL;

    fd = _open_noatime(path, O_NONBLOCK);
    if (fd == -1)
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);

    attr = 0;
    rc = ioctl(fd, FS_IOC_GETFLAGS, &attr);
    if (rc == -1)
    {
        close(fd);
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
    }

    close(fd);
    return Py_BuildValue("I", attr);
}
#endif /* def BUP_HAVE_FILE_ATTRS */


#ifdef BUP_HAVE_FILE_ATTRS
static PyObject *bup_set_linux_file_attr(PyObject *self, PyObject *args)
{
    int rc;
    unsigned int orig_attr, attr;
    char *path;
    int fd;

    if (!PyArg_ParseTuple(args, "sI", &path, &attr))
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
    rc = ioctl(fd, FS_IOC_GETFLAGS, &orig_attr);
    if (rc == -1)
    {
        close(fd);
        return PyErr_SetFromErrnoWithFilename(PyExc_OSError, path);
    }
    attr |= (orig_attr & FS_EXTENT_FL);

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


#define INTEGRAL_ASSIGNMENT_FITS(dest, src)                             \
    ({                                                                  \
        *(dest) = (src);                                                \
        *(dest) == (src) && (*(dest) < 1) == ((src) < 1);               \
    })


#define ASSIGN_PYLONG_TO_INTEGRAL(dest, pylong, overflow) \
    ({                                                     \
        int result = 0;                                                 \
        *(overflow) = 0;                                                \
        const long long ltmp = PyLong_AsLongLong(pylong);               \
        if (ltmp == -1 && PyErr_Occurred())                             \
        {                                                               \
            if (PyErr_ExceptionMatches(PyExc_OverflowError))            \
            {                                                           \
                const unsigned long ultmp = PyLong_AsUnsignedLongLong(pylong); \
                if (ultmp == (unsigned long long) -1 && PyErr_Occurred()) \
                {                                                       \
                    if (PyErr_ExceptionMatches(PyExc_OverflowError))    \
                    {                                                   \
                        PyErr_Clear();                                  \
                        *(overflow) = 1;                                \
                    }                                                   \
                }                                                       \
                if (INTEGRAL_ASSIGNMENT_FITS((dest), ultmp))            \
                    result = 1;                                         \
                else                                                    \
                    *(overflow) = 1;                                    \
            }                                                           \
        }                                                               \
        else                                                            \
        {                                                               \
            if (INTEGRAL_ASSIGNMENT_FITS((dest), ltmp))                 \
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

    if (!PyArg_ParseTuple(args, "is((Ol)(Ol))i",
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

    if (!PyArg_ParseTuple(args, "s((OL)(OL))",
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


static void set_invalid_timespec_msg(const char *field,
                                     const long long sec,
                                     const long nsec,
                                     const char *filename,
                                     int fd)
{
    if (filename != NULL)
        PyErr_Format(PyExc_ValueError,
                     "invalid %s timespec (%lld %ld) for file \"%s\"",
                     field, sec, nsec, filename);
    else
        PyErr_Format(PyExc_ValueError,
                     "invalid %s timespec (%lld %ld) for file descriptor %d",
                     field, sec, nsec, fd);
}


static int normalize_timespec_values(const char *name,
                                     long long *sec,
                                     long *nsec,
                                     const char *filename,
                                     int fd)
{
    if (*nsec < -999999999 || *nsec > 999999999)
    {
        set_invalid_timespec_msg(name, *sec, *nsec, filename, fd);
        return 0;
    }
    if (*nsec < 0)
    {
        if (*sec == LONG_MIN)
        {
            set_invalid_timespec_msg(name, *sec, *nsec, filename, fd);
            return 0;
        }
        *nsec += 1000000000;
        *sec -= 1;
    }
    return 1;
}


#define INTEGER_TO_PY(x) \
    (((x) >= 0) ? PyLong_FromUnsignedLongLong(x) : PyLong_FromLongLong(x))


static PyObject *stat_struct_to_py(const struct stat *st,
                                   const char *filename,
                                   int fd)
{
    long long atime = st->st_atime;
    long long mtime = st->st_mtime;
    long long ctime = st->st_ctime;
    long atime_ns = BUP_STAT_ATIME_NS(st);
    long mtime_ns = BUP_STAT_MTIME_NS(st);
    long ctime_ns = BUP_STAT_CTIME_NS(st);

    if (!normalize_timespec_values("atime", &atime, &atime_ns, filename, fd))
        return NULL;
    if (!normalize_timespec_values("mtime", &mtime, &mtime_ns, filename, fd))
        return NULL;
    if (!normalize_timespec_values("ctime", &ctime, &ctime_ns, filename, fd))
        return NULL;

    // We can check the known (via POSIX) signed and unsigned types at
    // compile time, but not (easily) the unspecified types, so handle
    // those via INTEGER_TO_PY().
    return Py_BuildValue("OKOOOOOL(Ll)(Ll)(Ll)",
                         INTEGER_TO_PY(st->st_mode),
                         (unsigned PY_LONG_LONG) st->st_ino,
                         INTEGER_TO_PY(st->st_dev),
                         INTEGER_TO_PY(st->st_nlink),
                         INTEGER_TO_PY(st->st_uid),
                         INTEGER_TO_PY(st->st_gid),
                         INTEGER_TO_PY(st->st_rdev),
                         (PY_LONG_LONG) st->st_size,
                         (PY_LONG_LONG) atime,
                         (long) atime_ns,
                         (PY_LONG_LONG) mtime,
                         (long) mtime_ns,
                         (PY_LONG_LONG) ctime,
                         (long) ctime_ns);
}


static PyObject *bup_stat(PyObject *self, PyObject *args)
{
    int rc;
    char *filename;

    if (!PyArg_ParseTuple(args, "s", &filename))
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

    if (!PyArg_ParseTuple(args, "s", &filename))
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


static PyMethodDef helper_methods[] = {
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
    { NULL, NULL, 0, NULL },  // sentinel
};


PyMODINIT_FUNC init_helpers(void)
{
    // FIXME: migrate these tests to configure.  Check against the
    // type we're going to use when passing to python.  Other stat
    // types are tested at runtime.
    assert(sizeof(ino_t) <= sizeof(unsigned PY_LONG_LONG));
    assert(sizeof(off_t) <= sizeof(PY_LONG_LONG));
    assert(sizeof(blksize_t) <= sizeof(PY_LONG_LONG));
    assert(sizeof(blkcnt_t) <= sizeof(PY_LONG_LONG));
    // Just be sure (relevant when passing timestamps back to Python above).
    assert(sizeof(PY_LONG_LONG) <= sizeof(long long));

    char *e;
    PyObject *m = Py_InitModule("_helpers", helper_methods);
    if (m == NULL)
        return;

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

    e = getenv("BUP_FORCE_TTY");
    istty2 = isatty(2) || (atoi(e ? e : "0") & 2);
    unpythonize_argv();
}
