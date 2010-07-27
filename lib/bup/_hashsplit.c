#include <Python.h>
#include <assert.h>
#include <stdint.h>
#include <fcntl.h>

#define BLOBBITS (13)
#define BLOBSIZE (1<<BLOBBITS)
#define WINDOWBITS (7)
#define WINDOWSIZE (1<<(WINDOWBITS-1))


typedef struct {
    uint32_t sum;
    uint8_t window[WINDOWSIZE];
    int wofs;
} Rollsum;


// FIXME: replace this with a not-stupid rolling checksum algorithm,
// such as the one used in rsync (Adler32?)
static void rollsum_add(Rollsum *r, uint8_t drop, uint8_t add)
{
    r->sum = ((r->sum<<1) | (r->sum>>31)) ^ drop ^ add;
}


static void rollsum_init(Rollsum *r)
{
    r->sum = r->wofs = 0;
    memset(r->window, 0, WINDOWSIZE);
}


// For some reason, gcc 4.3 (at least) optimizes badly if find_ofs()
// is static and rollsum_roll is an inline function.  Let's use a macro
// here instead to help out the optimizer.
#define rollsum_roll(r, ch) do { \
    rollsum_add((r), (r)->window[(r)->wofs], (ch)); \
    (r)->window[(r)->wofs] = (ch); \
    (r)->wofs = ((r)->wofs + 1) % WINDOWSIZE; \
} while (0)


static uint32_t rollsum_sum(uint8_t *buf, size_t ofs, size_t len)
{
    int count;
    Rollsum r;
    rollsum_init(&r);
    for (count = ofs; count < len; count++)
	rollsum_roll(&r, buf[count]);
    return r.sum;
}


static PyObject *selftest(PyObject *self, PyObject *args)
{
    uint8_t buf[100000];
    uint32_t sum1a, sum1b, sum2a, sum2b, sum3a, sum3b;
    int count;
    
    if (!PyArg_ParseTuple(args, ""))
	return NULL;
    
    srandom(1);
    for (count = 0; count < sizeof(buf); count++)
	buf[count] = random();
    
    sum1a = rollsum_sum(buf, 0, sizeof(buf));
    sum1b = rollsum_sum(buf, 1, sizeof(buf));
    sum2a = rollsum_sum(buf, sizeof(buf) - WINDOWSIZE*5/2,
			sizeof(buf) - WINDOWSIZE);
    sum2b = rollsum_sum(buf, 0, sizeof(buf) - WINDOWSIZE);
    sum3a = rollsum_sum(buf, 0, WINDOWSIZE+3);
    sum3b = rollsum_sum(buf, 3, WINDOWSIZE+3);
    
    fprintf(stderr, "sum1a = 0x%08x\n", sum1a);
    fprintf(stderr, "sum1b = 0x%08x\n", sum1b);
    fprintf(stderr, "sum2a = 0x%08x\n", sum2a);
    fprintf(stderr, "sum2b = 0x%08x\n", sum2b);
    fprintf(stderr, "sum3a = 0x%08x\n", sum3a);
    fprintf(stderr, "sum3b = 0x%08x\n", sum3b);
    
    return Py_BuildValue("i", sum1a==sum1b && sum2a==sum2b && sum3a==sum3b);
}


static int find_ofs(const unsigned char *buf, int len, int *bits)
{
    Rollsum r;
    int count;
    
    rollsum_init(&r);
    for (count = 0; count < len; count++)
    {
	rollsum_roll(&r, buf[count]);
	if ((r.sum & (BLOBSIZE-1)) == ((~0) & (BLOBSIZE-1)))
	{
	    if (bits)
	    {
		*bits = BLOBBITS;
		r.sum >>= BLOBBITS;
		for (*bits = BLOBBITS; (r.sum >>= 1) & 1; (*bits)++)
		    ;
	    }
	    return count+1;
	}
    }
    return 0;
}


static PyObject *blobbits(PyObject *self, PyObject *args)
{
    if (!PyArg_ParseTuple(args, ""))
	return NULL;
    return Py_BuildValue("i", BLOBBITS);
}


static PyObject *splitbuf(PyObject *self, PyObject *args)
{
    unsigned char *buf = NULL;
    int len = 0, out = 0, bits = -1;

    if (!PyArg_ParseTuple(args, "t#", &buf, &len))
	return NULL;
    out = find_ofs(buf, len, &bits);
    return Py_BuildValue("ii", out, bits);
}


static PyObject *bitmatch(PyObject *self, PyObject *args)
{
    unsigned char *buf1 = NULL, *buf2 = NULL;
    int len1 = 0, len2 = 0;
    int byte, bit;

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
    
    return Py_BuildValue("i", byte*8 + bit);
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
    int fd = -1, seed = 0;
    ssize_t ret;
    long long len = 0, kbytes = 0, written = 0;

    if (!PyArg_ParseTuple(args, "iLi", &fd, &len, &seed))
	return NULL;
    
    srandom(seed);
    
    for (kbytes = 0; kbytes < len/1024; kbytes++)
    {
	int i;
	for (i = 0; i < sizeof(buf)/sizeof(buf[0]); i++)
	    buf[i] = random();
	ret = write(fd, buf, sizeof(buf));
	if (ret < 0)
	    ret = 0;
	written += ret;
	if (ret < sizeof(buf))
	    break;
	if (kbytes/1024 > 0 && !(kbytes%1024))
	    fprintf(stderr, "Random: %lld Mbytes\r", kbytes/1024);
    }
    
    // handle non-multiples of 1024
    if (len % 1024)
    {
	int i;
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


static PyObject *open_noatime(PyObject *self, PyObject *args)
{
    char *filename = NULL;
    int attrs, attrs_noatime, fd;
    if (!PyArg_ParseTuple(args, "s", &filename))
	return NULL;
    attrs = O_RDONLY;
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
    if (fd < 0)
	return PyErr_SetFromErrnoWithFilename(PyExc_IOError, filename);
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


static PyMethodDef hashsplit_methods[] = {
    { "selftest", selftest, METH_VARARGS,
	"Check that the rolling checksum rolls correctly (for unit tests)." },
    { "blobbits", blobbits, METH_VARARGS,
	"Return the number of bits in the rolling checksum." },
    { "splitbuf", splitbuf, METH_VARARGS,
	"Split a list of strings based on a rolling checksum." },
    { "bitmatch", bitmatch, METH_VARARGS,
	"Count the number of matching prefix bits between two strings." },
    { "write_random", write_random, METH_VARARGS,
	"Write random bytes to the given file descriptor" },
    { "open_noatime", open_noatime, METH_VARARGS,
	"open() the given filename for read with O_NOATIME if possible" },
    { "fadvise_done", fadvise_done, METH_VARARGS,
	"Inform the kernel that we're finished with earlier parts of a file" },
    { NULL, NULL, 0, NULL },  // sentinel
};

PyMODINIT_FUNC init_hashsplit(void)
{
    Py_InitModule("_hashsplit", hashsplit_methods);
}
