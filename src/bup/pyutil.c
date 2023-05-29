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
