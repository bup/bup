#pragma once

#include <sys/types.h>

#include "bup/intprops.h"

#define BUP_LONGISH_TO_PY(x) \
    EXPR_SIGNED(x) ? PyLong_FromLongLong(x) : PyLong_FromUnsignedLongLong(x)

void *checked_calloc(size_t n, size_t size);
void *checked_malloc(size_t n, size_t size);
