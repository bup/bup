#include <Python.h>
#include <assert.h>
#include <stdint.h>

#define BLOBBITS (13)
#define BLOBSIZE (1<<BLOBBITS)
#define WINDOWBITS (7)
#define WINDOWSIZE (1<<(WINDOWBITS-1))


// FIXME: replace this with a not-stupid rolling checksum algorithm,
// such as the one used in rsync (Adler32?)
static uint32_t stupidsum_add(uint32_t old, uint8_t drop, uint8_t add)
{
    return ((old<<1) | (old>>31)) ^ drop ^ add;
}


static int find_ofs(const unsigned char *buf, int len)
{
    unsigned char window[WINDOWSIZE];
    uint32_t sum = 0;
    int i = 0, count;
    memset(window, 0, sizeof(window));
    
    for (count = 0; count < len; count++)
    {
	sum = stupidsum_add(sum, window[i], buf[count]);
	window[i] = buf[count];
	i = (i + 1) % WINDOWSIZE;
	if ((sum & (BLOBSIZE-1)) == ((~0) & (BLOBSIZE-1)))
	    return count+1;
    }
    return 0;
}


static PyObject *splitbuf(PyObject *self, PyObject *args)
{
    unsigned char *buf = NULL;
    int len = 0, out = 0;

    if (!PyArg_ParseTuple(args, "t#", &buf, &len))
	return NULL;
    out = find_ofs(buf, len);
    //return Py_BuildValue("i", len);//len>BLOBSIZE ? BLOBSIZE : len);
    return Py_BuildValue("i", out);
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
    
    for (kbytes = len/1024; kbytes > 0; kbytes--)
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
	if (!(kbytes%1024))
	    fprintf(stderr, ".");
    }
    
    return Py_BuildValue("L", written);
}


static PyMethodDef hashsplit_methods[] = {
    { "splitbuf", splitbuf, METH_VARARGS,
	"Split a list of strings based on a rolling checksum." },
    { "bitmatch", bitmatch, METH_VARARGS,
	"Count the number of matching prefix bits between two strings." },
    { "write_random", write_random, METH_VARARGS,
	"Write random bytes to the given file descriptor" },
    { NULL, NULL, 0, NULL },  // sentinel
};

PyMODINIT_FUNC init_hashsplit(void)
{
    Py_InitModule("_hashsplit", hashsplit_methods);
}
