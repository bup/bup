#define _LARGEFILE64_SOURCE 1
#define PY_SSIZE_T_CLEAN 1
#undef NDEBUG
#include "../config/config.h"

// According to Python, its header has to go first:
//   http://docs.python.org/3/c-api/intro.html#include-files
#include <Python.h>

#include "bup/compat.h"

#if PY_MAJOR_VERSION == 3 && PY_MINOR_VERSION < 8
# define bup_py_main bup_py_bytes_main
#else
# define bup_py_main Py_BytesMain
#endif

int main(int argc, char **argv)
{
    assert(argc > 0);
    return bup_py_main (argc, argv);
}
