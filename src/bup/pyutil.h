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
