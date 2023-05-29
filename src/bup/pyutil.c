#define _LARGEFILE64_SOURCE 1
#define PY_SSIZE_T_CLEAN 1
#undef NDEBUG
#include "../../config/config.h"

// According to Python, its header has to go first:
//   http://docs.python.org/3/c-api/intro.html#include-files
#include <Python.h>

#include "bup/pyutil.h"

#include "bup/intprops.h"


void *checked_calloc(size_t n, size_t size)
{
    void *result = calloc(n, size);
    if (!result)
        PyErr_NoMemory();
    return result;
}

void *checked_malloc(size_t n, size_t size)
{
    size_t total;
    if (!INT_MULTIPLY_OK(n, size, &total))
    {
        PyErr_Format(PyExc_OverflowError,
                     "request to allocate %zu items of size %zu is too large",
                     n, size);
        return NULL;
    }
    void *result = malloc(total);
    if (!result)
        return PyErr_NoMemory();
    return result;
}

int bup_ulong_from_py(unsigned long *x, PyObject *py, const char *name)
{
    if (!PyLong_Check(py))
    {
        PyErr_Format(PyExc_TypeError, "%s expected integer, not %R", name, py);
        return 0;
    }

    const unsigned long tmp = PyLong_AsUnsignedLong(py);
    if (PyErr_Occurred())
    {
        if (PyErr_ExceptionMatches(PyExc_OverflowError))
            PyErr_Format(PyExc_OverflowError, "%s overflows unsigned long: %R",
                         name, py);
        return 0;
    }
    *x = tmp;
    return 1;
}

int bup_uint_from_py(unsigned int *x, PyObject *py, const char *name)
{
    unsigned long tmp;
    if (!bup_ulong_from_py(&tmp, py, name))
        return 0;

    if (tmp > UINT_MAX)
    {
        PyErr_Format(PyExc_OverflowError, "%s overflows unsigned int: %R",
                     name, py);
        return 0;
    }
    *x = (unsigned int) tmp;
    return 1;
}

int bup_ullong_from_py(unsigned PY_LONG_LONG *x, PyObject *py, const char *name)
{
    if (!PyLong_Check(py))
    {
        PyErr_Format(PyExc_TypeError, "%s expected integer, not %R", name, py);
        return 0;
    }

    const unsigned PY_LONG_LONG tmp = PyLong_AsUnsignedLongLong(py);
    if (tmp == (unsigned long long) -1 && PyErr_Occurred())
    {
        if (PyErr_ExceptionMatches(PyExc_OverflowError))
            PyErr_Format(PyExc_OverflowError,
                         "%s overflows unsigned long long: %R", name, py);
        return 0;
    }
    *x = tmp;
    return 1;
}
