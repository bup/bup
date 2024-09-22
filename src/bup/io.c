
#define _GNU_SOURCE  1
#undef NDEBUG

#include <stdarg.h>
#include <stdlib.h>

#include "bup.h"
#include "bup/io.h"

__attribute__ ((format(printf, 2, 3)))
void
msg(FILE* f, const char * const msg, ...)
{
    if (fputs("bup: ", f) == EOF)
        exit(BUP_EXIT_FAILURE);
    va_list ap;
    va_start(ap, msg);
    if (vfprintf(f, msg, ap) < 0)
        exit(BUP_EXIT_FAILURE);
    va_end(ap);
}

__attribute__ ((format(printf, 2, 3)))
void
die(int exit_status, const char * const msg, ...)
{
    if (fputs("bup: ", stderr) == EOF)
        exit(BUP_EXIT_FAILURE);
    va_list ap;
    va_start(ap, msg);
    if (vfprintf(stderr, msg, ap) < 0)
        exit(BUP_EXIT_FAILURE);
    va_end(ap);
    exit(exit_status);
}
