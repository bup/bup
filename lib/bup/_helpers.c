#define _LARGEFILE64_SOURCE 1

#include "bupsplit.h"
#include <Python.h>
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <arpa/inet.h>
#include <stdint.h>

#ifdef linux
#include <linux/fs.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/time.h>
#endif


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
    int len = 0, out = 0, bits = -1;

    if (!PyArg_ParseTuple(args, "t#", &buf, &len))
	return NULL;
    out = bupsplit_find_ofs(buf, len, &bits);
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


static PyObject *firstword(PyObject *self, PyObject *args)
{
    unsigned char *buf = NULL;
    int len = 0;
    uint32_t v;

    if (!PyArg_ParseTuple(args, "t#", &buf, &len))
	return NULL;
    
    if (len < 4)
	return NULL;
    
    v = ntohl(*(uint32_t *)buf);
    return Py_BuildValue("I", v);
}


static PyObject *extract_bits(PyObject *self, PyObject *args)
{
    unsigned char *buf = NULL;
    int len = 0, nbits = 0;
    uint32_t v, mask;

    if (!PyArg_ParseTuple(args, "t#i", &buf, &len, &nbits))
	return NULL;
    
    if (len < 4)
	return NULL;
    
    mask = (1<<nbits) - 1;
    v = ntohl(*(uint32_t *)buf);
    v = (v >> (32-nbits)) & mask;
    return Py_BuildValue("I", v);
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
	unsigned i;
	for (i = 0; i < sizeof(buf)/sizeof(buf[0]); i++)
	    buf[i] = random();
	ret = write(fd, buf, sizeof(buf));
	if (ret < 0)
	    ret = 0;
	written += ret;
	if (ret < (int)sizeof(buf))
	    break;
	if (kbytes/1024 > 0 && !(kbytes%1024))
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


#ifdef linux
static PyObject *bup_get_linux_file_attr(PyObject *self, PyObject *args)
{
    int rc;
    unsigned long attr;
    char *path;
    int fd;

    if (!PyArg_ParseTuple(args, "s", &path))
        return NULL;

    fd = open(path, O_RDONLY | O_NONBLOCK | O_LARGEFILE | O_NOFOLLOW);
    if (fd == -1)
        return PyErr_SetFromErrnoWithFilename(PyExc_IOError, path);

    attr = 0;
    rc = ioctl(fd, FS_IOC_GETFLAGS, &attr);
    if (rc == -1)
    {
        close(fd);
        return PyErr_SetFromErrnoWithFilename(PyExc_IOError, path);
    }

    close(fd);
    return Py_BuildValue("k", attr);
}


static PyObject *bup_set_linux_file_attr(PyObject *self, PyObject *args)
{
    int rc;
    unsigned long attr;
    char *path;
    int fd;

    if (!PyArg_ParseTuple(args, "sk", &path, &attr))
        return NULL;

    fd = open(path, O_RDONLY | O_NONBLOCK | O_LARGEFILE | O_NOFOLLOW);
    if(fd == -1)
        return PyErr_SetFromErrnoWithFilename(PyExc_IOError, path);

    rc = ioctl(fd, FS_IOC_SETFLAGS, &attr);
    if (rc == -1)
    {
        close(fd);
        return PyErr_SetFromErrnoWithFilename(PyExc_IOError, path);
    }

    close(fd);
    Py_RETURN_TRUE;
}
#endif /* def linux */


#if _XOPEN_SOURCE >= 700 || _POSIX_C_SOURCE >= 200809L
#define HAVE_BUP_UTIMENSAT 1

static PyObject *bup_utimensat(PyObject *self, PyObject *args)
{
    int rc, dirfd, flags;
    char *path;
    long access, access_ns, modification, modification_ns;
    struct timespec ts[2];

    if (!PyArg_ParseTuple(args, "is((ll)(ll))i",
                          &dirfd,
                          &path,
                          &access, &access_ns,
                          &modification, &modification_ns,
                          &flags))
        return NULL;

    if (isnan(access))
    {
        PyErr_SetString(PyExc_ValueError, "access time is NaN");
        return NULL;
    }
    else if (isinf(access))
    {
        PyErr_SetString(PyExc_ValueError, "access time is infinite");
        return NULL;
    }
    else if (isnan(modification))
    {
        PyErr_SetString(PyExc_ValueError, "modification time is NaN");
        return NULL;
    }
    else if (isinf(modification))
    {
        PyErr_SetString(PyExc_ValueError, "modification time is infinite");
        return NULL;
    }

    if (isnan(access_ns))
    {
        PyErr_SetString(PyExc_ValueError, "access time ns is NaN");
        return NULL;
    }
    else if (isinf(access_ns))
    {
        PyErr_SetString(PyExc_ValueError, "access time ns is infinite");
        return NULL;
    }
    else if (isnan(modification_ns))
    {
        PyErr_SetString(PyExc_ValueError, "modification time ns is NaN");
        return NULL;
    }
    else if (isinf(modification_ns))
    {
        PyErr_SetString(PyExc_ValueError, "modification time ns is infinite");
        return NULL;
    }

    ts[0].tv_sec = access;
    ts[0].tv_nsec = access_ns;
    ts[1].tv_sec = modification;
    ts[1].tv_nsec = modification_ns;

    rc = utimensat(dirfd, path, ts, flags);
    if (rc != 0)
        return PyErr_SetFromErrnoWithFilename(PyExc_IOError, path);

    Py_RETURN_TRUE;
}

#endif /* _XOPEN_SOURCE >= 700 || _POSIX_C_SOURCE >= 200809L */


#ifdef linux /* and likely others */

#define HAVE_BUP_STAT 1
static PyObject *bup_stat(PyObject *self, PyObject *args)
{
    int rc;
    char *filename;

    if (!PyArg_ParseTuple(args, "s", &filename))
        return NULL;

    struct stat st;
    rc = stat(filename, &st);
    if (rc != 0)
        return PyErr_SetFromErrnoWithFilename(PyExc_IOError, filename);

    return Py_BuildValue("kkkkkkkk"
                         "(ll)"
                         "(ll)"
                         "(ll)",
                         (unsigned long) st.st_mode,
                         (unsigned long) st.st_ino,
                         (unsigned long) st.st_dev,
                         (unsigned long) st.st_nlink,
                         (unsigned long) st.st_uid,
                         (unsigned long) st.st_gid,
                         (unsigned long) st.st_rdev,
                         (unsigned long) st.st_size,
                         (long) st.st_atime,
                         (long) st.st_atim.tv_nsec,
                         (long) st.st_mtime,
                         (long) st.st_mtim.tv_nsec,
                         (long) st.st_ctime,
                         (long) st.st_ctim.tv_nsec);
}


#define HAVE_BUP_LSTAT 1
static PyObject *bup_lstat(PyObject *self, PyObject *args)
{
    int rc;
    char *filename;

    if (!PyArg_ParseTuple(args, "s", &filename))
        return NULL;

    struct stat st;
    rc = lstat(filename, &st);
    if (rc != 0)
        return PyErr_SetFromErrnoWithFilename(PyExc_IOError, filename);

    return Py_BuildValue("kkkkkkkk"
                         "(ll)"
                         "(ll)"
                         "(ll)",
                         (unsigned long) st.st_mode,
                         (unsigned long) st.st_ino,
                         (unsigned long) st.st_dev,
                         (unsigned long) st.st_nlink,
                         (unsigned long) st.st_uid,
                         (unsigned long) st.st_gid,
                         (unsigned long) st.st_rdev,
                         (unsigned long) st.st_size,
                         (long) st.st_atime,
                         (long) st.st_atim.tv_nsec,
                         (long) st.st_mtime,
                         (long) st.st_mtim.tv_nsec,
                         (long) st.st_ctime,
                         (long) st.st_ctim.tv_nsec);
}


#define HAVE_BUP_FSTAT 1
static PyObject *bup_fstat(PyObject *self, PyObject *args)
{
    int rc, fd;

    if (!PyArg_ParseTuple(args, "i", &fd))
        return NULL;

    struct stat st;
    rc = fstat(fd, &st);
    if (rc != 0)
        return PyErr_SetFromErrno(PyExc_IOError);

    return Py_BuildValue("kkkkkkkk"
                         "(ll)"
                         "(ll)"
                         "(ll)",
                         (unsigned long) st.st_mode,
                         (unsigned long) st.st_ino,
                         (unsigned long) st.st_dev,
                         (unsigned long) st.st_nlink,
                         (unsigned long) st.st_uid,
                         (unsigned long) st.st_gid,
                         (unsigned long) st.st_rdev,
                         (unsigned long) st.st_size,
                         (long) st.st_atime,
                         (long) st.st_atim.tv_nsec,
                         (long) st.st_mtime,
                         (long) st.st_mtim.tv_nsec,
                         (long) st.st_ctime,
                         (long) st.st_ctim.tv_nsec);
}

#endif /* def linux */


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
    { "extract_bits", extract_bits, METH_VARARGS,
	"Take the first 'nbits' bits from 'buf' and return them as an int." },
    { "write_random", write_random, METH_VARARGS,
	"Write random bytes to the given file descriptor" },
    { "open_noatime", open_noatime, METH_VARARGS,
	"open() the given filename for read with O_NOATIME if possible" },
    { "fadvise_done", fadvise_done, METH_VARARGS,
	"Inform the kernel that we're finished with earlier parts of a file" },
#ifdef linux
    { "get_linux_file_attr", bup_get_linux_file_attr, METH_VARARGS,
      "Return the Linux attributes for the given file." },
    { "set_linux_file_attr", bup_set_linux_file_attr, METH_VARARGS,
      "Set the Linux attributes for the given file." },
#endif
#ifdef HAVE_BUP_UTIMENSAT
    { "utimensat", bup_utimensat, METH_VARARGS,
      "Change file timestamps with nanosecond precision." },
#endif
#ifdef HAVE_BUP_STAT
    { "stat", bup_stat, METH_VARARGS,
      "Extended version of stat." },
#endif
#ifdef HAVE_BUP_LSTAT
    { "lstat", bup_lstat, METH_VARARGS,
      "Extended version of lstat." },
#endif
#ifdef HAVE_BUP_FSTAT
    { "fstat", bup_fstat, METH_VARARGS,
      "Extended version of fstat." },
#endif
    { NULL, NULL, 0, NULL },  // sentinel
};


PyMODINIT_FUNC init_helpers(void)
{
    PyObject *m = Py_InitModule("_helpers", helper_methods);
    if (m == NULL)
        return;
#ifdef HAVE_BUP_UTIMENSAT
    PyModule_AddObject(m, "AT_FDCWD", Py_BuildValue("i", AT_FDCWD));
    PyModule_AddObject(m, "AT_SYMLINK_NOFOLLOW",
                       Py_BuildValue("i", AT_SYMLINK_NOFOLLOW));
#endif
#ifdef HAVE_BUP_STAT
    Py_INCREF(Py_True);
    PyModule_AddObject(m, "_have_ns_fs_timestamps", Py_True);
#else
    Py_INCREF(Py_False);
    PyModule_AddObject(m, "_have_ns_fs_timestamps", Py_False);
#endif
}
