#pragma once

#include <sys/types.h>

#include "bup/intprops.h"

#define BUP_LONGISH_TO_PY(x) \
    EXPR_SIGNED(x) ? PyLong_FromLongLong(x) : PyLong_FromUnsignedLongLong(x)

void *checked_calloc(size_t n, size_t size);
void *checked_malloc(size_t n, size_t size);

int bup_uint_from_py(unsigned int *x, PyObject *py, const char *name);
int bup_ulong_from_py(unsigned long *x, PyObject *py, const char *name);
int bup_ullong_from_py(unsigned long long *x, PyObject *py, const char *name);

// Currently only up to signed/unsigned long long given py api.  On
// success returns non-zero.  On failure returns 0 and overflow will
// be non-zero if there was an overflow, otherwise a python exception
// will be pending.
#define BUP_ASSIGN_PYLONG_TO_INTEGRAL(dest, pylong, overflow)           \
    ({                                                                  \
         int result = 0;                                                \
         int pending_overflow = 0;                                      \
         if (EXPR_SIGNED(dest)) {                                       \
             const long long tmp = PyLong_AsLongLong(pylong);           \
             if (tmp == -1 && PyErr_Occurred()                          \
                 && PyErr_ExceptionMatches(PyExc_OverflowError))        \
                 pending_overflow = 2;                                  \
             else {                                                     \
                 if (INTEGRAL_ASSIGNMENT_FITS((dest), tmp))             \
                     result = 1;                                        \
                 else                                                   \
                     pending_overflow = 1;                              \
             }                                                          \
         } else {                                                       \
             const unsigned long long tmp =                             \
                 PyLong_AsUnsignedLongLong(pylong);                     \
             if (tmp == (unsigned long long) -1 && PyErr_Occurred()     \
                 && PyErr_ExceptionMatches(PyExc_OverflowError))        \
                 pending_overflow = 2;                                  \
             else {                                                     \
                 if (INTEGRAL_ASSIGNMENT_FITS((dest), tmp))             \
                     result = 1;                                        \
                 else                                                   \
                     pending_overflow = 1;                              \
             }                                                          \
         }                                                              \
         if (pending_overflow == 2) {                                   \
             PyErr_Clear();                                             \
             *(overflow) = 1;                                           \
         }                                                              \
         result;                                                        \
    })
