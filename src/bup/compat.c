
#define PY_SSIZE_T_CLEAN
#define _GNU_SOURCE  1 // asprintf
#undef NDEBUG

// According to Python, its header has to go first:
//   http://docs.python.org/3/c-api/intro.html#include-files
#include <Python.h>

#include "bup.h"
#include "bup/compat.h"
#include "bup/io.h"

#if PY_MAJOR_VERSION == 3 && PY_MINOR_VERSION < 8

int bup_py_bytes_main(int argc, char **argv)
{
    assert(argc > 0);
    wchar_t **wargv = PyMem_RawMalloc(argc * sizeof(wchar_t *));
    if (!wargv)
        die(BUP_EXIT_FAILURE, "memory insufficient to decode command line arguments");
    int i;
    for (i = 0; i < argc; i++) {
        size_t wargn;
        wargv[i] = Py_DecodeLocale(argv[i], &wargn);
        if (!wargv[i]) {
            switch (wargn) {
            case (size_t) -1:
                die(BUP_EXIT_FAILURE, "too little memory to decode command line argument %d\n",
                    i);
                break;
            case (size_t) -2:
                die(BUP_EXIT_FAILURE, "unable to decode command line argument %d\n", i);
                break;
            default:
                die(BUP_EXIT_FAILURE, "unexpected error from Py_DecodeLocale(): %zu\n", wargn);
                break;
            }
            exit(BUP_EXIT_FAILURE);
        }
    }
    return Py_Main(argc, wargv);
}

#endif // PY_MAJOR_VERSION == 3 && PY_MINOR_VERSION < 8
