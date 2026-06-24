#pragma once

#include <sys/types.h>

#include "bup/intprops.h"

#define BUP_LONGISH_TO_PY(x) \
    EXPR_SIGNED(x) ? PyLong_FromLongLong(x) : PyLong_FromUnsignedLongLong(x)

void *checked_calloc(size_t n, size_t size);
void *checked_malloc(size_t n, size_t size);

int bup_int_from_py(int *x, PyObject *py, const char *name);
int bup_uint_from_py(unsigned int *x, PyObject *py, const char *name);
int bup_ulong_from_py(unsigned long *x, PyObject *py, const char *name);
int bup_ullong_from_py(unsigned long long *x, PyObject *py, const char *name);

// Currently only up to signed/unsigned long long given py api.  On
// success returns non-zero.  On failure returns 0 and overflow will
// be non-zero if there was an overflow, otherwise a python exception
// will be pending.
#define BUP_ASSIGN_PYLONG_TO_INTEGRAL(dest, pylong, overflow)           \
    ({                                                                  \
         int res___ = 0;                                                \
         __auto_type pylong___ = (pylong);                              \
         __auto_type overflow___ = (overflow);                          \
         if (EXPR_SIGNED(*(dest))) {                                    \
             const long long tmp___ = PyLong_AsLongLong(pylong___);     \
             if (tmp___ == -1 && PyErr_Occurred()                       \
                 && PyErr_ExceptionMatches(PyExc_OverflowError)) {      \
                 PyErr_Clear();                                         \
                 *overflow___ = 1;                                      \
             } else {                                                   \
                 if (INT_ADD_OK(tmp___, 0, (dest)))                     \
                     res___ = 1;                                        \
                 else                                                   \
                     *overflow___ = 1;                                  \
             }                                                          \
         } else {                                                       \
             const unsigned long long tmp___ =                          \
                 PyLong_AsUnsignedLongLong(pylong___);                  \
             if (tmp___ == (unsigned long long) -1 && PyErr_Occurred()  \
                 && PyErr_ExceptionMatches(PyExc_OverflowError)) {      \
                 PyErr_Clear();                                         \
                 *overflow___ = 1;                                      \
             } else {                                                   \
                 if (INT_ADD_OK(tmp___, 0, (dest)))                     \
                     res___ = 1;                                        \
                 else                                                   \
                     *overflow___ = 1;                                  \
             }                                                          \
         }                                                              \
         res___;                                                        \
    })
