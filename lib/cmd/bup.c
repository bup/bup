
#define PY_SSIZE_T_CLEAN
#define _GNU_SOURCE  1 // asprintf
#undef NDEBUG

// According to Python, its header has to go first:
//   http://docs.python.org/3/c-api/intro.html#include-files
#include <Python.h>

// pyupgrade *: adjust
#if PY_MAJOR_VERSION < 3 || (PY_MAJOR_VERSION == 3 && PY_MINOR_VERSION < 7)
#define BUP_STR(x) #x
#define BUP_XSTR(x) BUP_STR(x)
#pragma message "Python versions older than 3.7 are not supported; detected X.Y " \
    BUP_XSTR(PY_MAJOR_VERSION) "." BUP_XSTR(PY_MINOR_VERSION)
#error "Halting"
#endif

#include <libgen.h>
#include <limits.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#if defined(__FreeBSD__) || defined(__NetBSD__)
# include <sys/sysctl.h>
#endif
#include <sys/types.h>
#include <unistd.h>

#include "bup.h"
#include "bup/compat.h"
#include "bup/intprops.h"
#include "bup/io.h"

static int prog_argc = 0;
static char **prog_argv = NULL;
static char *orig_env_pythonpath = NULL;

// pyupgrade 3.8+: reconsider
static PyObject*
get_argv(PyObject *self, PyObject *args) // https://bugs.python.org/issue35883
{
    if (!PyArg_ParseTuple(args, ""))
	return NULL;

    PyObject *result = PyList_New(prog_argc);
    int i;
    for (i = 0; i < prog_argc; i++) {
        PyObject *s = PyBytes_FromString(prog_argv[i]);
        if (!s)
            die(BUP_EXIT_FAILURE, "cannot convert argument to bytes: %s\n", prog_argv[i]);
        PyList_SET_ITEM(result, i, s);
    }
    return result;
}

static PyMethodDef bup_main_methods[] = {
    {"argv", get_argv, METH_VARARGS,
     "Return the program's current argv array as a list of byte strings." },
    {NULL, NULL, 0, NULL}
};

static int setup_module(PyObject *mod)
{
    if (!orig_env_pythonpath) {
        PyObject_SetAttrString(mod, "env_pythonpath", Py_None);
    } else {
        PyObject *py_p = PyBytes_FromString(orig_env_pythonpath);
        if (!py_p)
            die(BUP_EXIT_FAILURE, "cannot convert PYTHONPATH to bytes: %s\n",
                orig_env_pythonpath);
        PyObject_SetAttrString(mod, "env_pythonpath", py_p);
        Py_DECREF(py_p);
    }
    return 1;
}

static struct PyModuleDef bup_main_module_def = {
    .m_base = PyModuleDef_HEAD_INIT,
    .m_name = "bup_main",
    .m_doc = "Built-in bup module providing direct access to argv.",
    .m_size = -1,
    .m_methods = bup_main_methods
};

static PyObject *
PyInit_bup_main(void) {
    PyObject *mod =  PyModule_Create(&bup_main_module_def);
    if (!setup_module(mod))
    {
        Py_DECREF(mod);
        return NULL;
    }
    return mod;
}

static void
setup_bup_main_module(void) {

    char *path = getenv("PYTHONPATH");
    if (path)
        orig_env_pythonpath = strdup(path);

    if (PyImport_AppendInittab("bup_main", PyInit_bup_main) == -1)
        die(BUP_EXIT_FAILURE, "unable to register bup_main module\n");
}

/*
 * Older realpath implementations (e.g. 4.4BSD) required the second
 * argument to be non-NULL, and then POSIX added the option of NULL
 * with the semantics of malloc'ing a big-enough buffer.  Define a
 * helper function with the NULL semantics to accomodate older
 * platforms.
 *
 * gnulib has a list of systems that are known to reject NULL as the
 * 2nd argument:
 *   https://www.gnu.org/software/gnulib/manual/html_node/realpath.html
 */

#define BUP_HAVE_POSIX_REALPATH

// FreeBSD < 7: bup's FreeBSD code does not use realpath(3)
#if defined(__NetBSD__)
#  if !__NetBSD_Prereq__(7,0,0)
#    undef BUP_HAVE_POSIX_REALPATH
#  endif
// OpenBSD: https://cvsweb.openbsd.org/cgi-bin/cvsweb/src/sys/sys/param.h.diff?r1=1.91&r2=1.92&f=h
#elif defined(__OpenBSD__) && __OpenBSD__ < 201111
#  undef BUP_HAVE_POSIX_REALPATH
#endif

#if ! defined(__FreeBSD__)
static char *
bup_realpath(const char *pathname)
{
#ifdef BUP_HAVE_POSIX_REALPATH
    return realpath(pathname, NULL);
#else
    char resolvedname[PATH_MAX];
    char *ret = realpath(pathname, resolvedname);
    if (ret != NULL) {
        assert(ret == resolvedname);
        ret = strdup(ret);
    }
    return ret;
#endif
}
#endif // not defined(__FreeBSD__)

#if defined(__APPLE__) && defined(__MACH__)

static char *exe_parent_dir(const char * const argv_0) {
    char *mpath = NULL;
    char spath[2048];
    uint32_t size = sizeof(spath);
    int rc = _NSGetExecutablePath(spath, &size);
    if (rc == -1) {
        mpath = malloc(size);
        if (!mpath) die(BUP_EXIT_FAILURE, "unable to allocate memory for executable path\n");
        rc = _NSGetExecutablePath(mpath, &size);
    }
    if(rc != 0) die(BUP_EXIT_FAILURE, "unable to find executable path\n");
    char *path = mpath ? mpath : spath;
    char *abs_exe = bup_realpath(path);
    if (!abs_exe)
        die(BUP_EXIT_FAILURE, "cannot resolve path (%s): %s\n", strerror(errno), path);
    char * const abs_parent = strdup(dirname(abs_exe));
    assert(abs_parent);
    if (mpath) free(mpath);
    free(abs_exe);
    return abs_parent;
}

#elif defined(__FreeBSD__)

static char *exe_path ()
{
    const int mib[] = {CTL_KERN, KERN_PROC, KERN_PROC_PATHNAME, -1};
    size_t path_len;
    int rc = sysctl (mib, 4, NULL, &path_len, NULL, 0);
    if (rc != 0) die(BUP_EXIT_FAILURE, "unable to determine executable path length\n");
    char *path = malloc (path_len);
    if (!path) die(BUP_EXIT_FAILURE, "unable to allocate memory for executable path\n");
    rc = sysctl (mib, 4, path, &path_len, NULL, 0);
    if (rc != 0) die(BUP_EXIT_FAILURE, "unable to determine executable path via sysctl\n");
    return path;
}

static char *exe_parent_dir(const char * const argv_0)
{
    char * const exe = exe_path();
    if (!exe) die(BUP_EXIT_FAILURE, "unable to determine executable path\n");
    char * const parent = strdup(dirname(exe));
    if (!parent) die(BUP_EXIT_FAILURE, "unable to determine parent directory of executable\n");
    free(exe);
    return parent;
}

#else // not defined(__FreeBSD__)

/// Use /proc if possible, and if all else fails, search in the PATH

#if defined(__linux__)
# define PROC_SELF_EXE "/proc/self/exe"
#elif defined(__sun) || defined (sun)
# define PROC_SELF_EXE "/proc/self/path/a.out"
#endif

static char *find_in_path(const char * const name, const char * const path)
{
    char *result = NULL;
    char *tmp_path = strdup(path);
    assert(tmp_path);
    const char *elt;
    char *tok_path = tmp_path;
    while ((elt = strtok(tok_path, ":")) != NULL) {
        tok_path = NULL;
        char *candidate;
        int rc = asprintf(&candidate, "%s/%s", elt, name);
        assert(rc >= 0);
        struct stat st;
        rc = stat(candidate, &st);
        if (rc != 0) {
            switch (errno) {
                case EACCES: case ELOOP: case ENOENT: case ENAMETOOLONG:
                case ENOTDIR:
                    break;
                default:
                    die(BUP_EXIT_FAILURE, "cannot stat %s: %s\n", candidate, strerror(errno));
                    break;
            }
        } else if (S_ISREG(st.st_mode)) {
            if (access(candidate, X_OK) == 0) {
                result = candidate;
                break;
            }
            switch (errno) {
                case EACCES: case ELOOP: case ENOENT: case ENAMETOOLONG:
                case ENOTDIR:
                    break;
                default:
                    die(BUP_EXIT_FAILURE, "cannot determine executability of %s: %s\n",
                        candidate, strerror(errno));
                    break;
            }
        }
        free(candidate);
    }
    free(tmp_path);
    return result;
}

static char *find_exe_parent(const char * const argv_0)
{
    char *candidate = NULL;
    const char * const slash = strchr(argv_0, '/');
    if (slash) {
        candidate = strdup(argv_0);
        assert(candidate);
    } else {
        const char * const env_path = getenv("PATH");
        if (!env_path)
            die(BUP_EXIT_FAILURE, "no PATH and executable isn't relative or absolute: %s\n",
                argv_0);
        char *path_exe = find_in_path(argv_0, env_path);
        if (path_exe) {
            char * abs_exe = bup_realpath(path_exe);
            if (!abs_exe)
                die(BUP_EXIT_FAILURE, "cannot resolve path (%s): %s\n",
                    strerror(errno), path_exe);
            free(path_exe);
            candidate = abs_exe;
        }
    }
    if (!candidate)
        return NULL;

    char * const abs_exe = bup_realpath(candidate);
    if (!abs_exe)
        die(BUP_EXIT_FAILURE, "cannot resolve path (%s): %s\n", strerror(errno), candidate);
    free(candidate);
    char * const abs_parent = strdup(dirname(abs_exe));
    assert(abs_parent);
    free(abs_exe);
    return abs_parent;
}

static char *exe_parent_dir(const char * const argv_0)
{
#ifdef PROC_SELF_EXE
    char sbuf[2048];
    char *path = sbuf;
    size_t path_n = sizeof(sbuf);
    ssize_t len;
    while (1) {
        len = readlink(PROC_SELF_EXE, path, path_n);
        if (len == -1 || (size_t) len != path_n)
            break;
        if (!INT_MULTIPLY_OK(path_n, 2, &path_n))
            die(BUP_EXIT_FAILURE, "memory buffer for executable path would be too big\n");
        if (path != sbuf) free(path);
        path = malloc(path_n);
        if (!path)
            die(BUP_EXIT_FAILURE, "unable to allocate memory for executable path\n");
    }
    if (len != -1) {
        path[len] = '\0';
        char *result = strdup(dirname(path));
        if (path != sbuf)
            free(path);
        return result;
    }
    switch (errno) {
    case ENOENT: case EACCES: case EINVAL: case ELOOP: case ENOTDIR:
    case ENAMETOOLONG:
        break;
    default:
        die(BUP_EXIT_FAILURE, "cannot resolve %s: %s\n", path, strerror(errno));
        break;
    }
    if (path != sbuf)
        free(path);
#endif
    return find_exe_parent(argv_0);
}

#endif // use /proc if possible, and if all else fails, search in the PATh

static void
setenv_or_die(const char *name, const char *value)
{
    int rc = setenv(name, value, 1);
    if (rc != 0)
        die(BUP_EXIT_FAILURE, "setenv %s=%s failed (%s)\n", name, value, strerror(errno));
}

static void
prepend_lib_to_pythonpath(const char * const exec_path,
                          const char * const relative_path)
{
    char *parent = exe_parent_dir(exec_path);
    assert(parent);
    char *bupmodpath;
    int rc = asprintf(&bupmodpath, "%s/%s", parent, relative_path);
    assert(rc >= 0);
    struct stat st;
    rc = stat(bupmodpath, &st);
    if (rc != 0)
        die(BUP_EXIT_FAILURE, "unable find lib dir (%s): %s\n", strerror(errno), bupmodpath);
    if (!S_ISDIR(st.st_mode))
        die(BUP_EXIT_FAILURE, "lib path is not dir: %s\n", bupmodpath);
    char *curpypath = getenv("PYTHONPATH");
    if (curpypath) {
        char *path;
        int rc = asprintf(&path, "%s:%s", bupmodpath, curpypath);
        assert(rc >= 0);
        setenv_or_die("PYTHONPATH", path);
        free(path);
    } else {
        setenv_or_die("PYTHONPATH", bupmodpath);
    }

    free(bupmodpath);
    free(parent);
}

#if PY_MAJOR_VERSION == 3 && PY_MINOR_VERSION < 8
# define bup_py_main bup_py_bytes_main
#else
# define bup_py_main Py_BytesMain
#endif

#if defined(BUP_DEV_BUP_PYTHON) && defined(BUP_DEV_BUP_EXEC)
# error "Both BUP_DEV_BUP_PYTHON and BUP_DEV_BUP_EXEC are defined"
#endif

#ifdef BUP_DEV_BUP_PYTHON

int main(int argc, char **argv)
{
    assert(argc > 0);
    prog_argc = argc;
    prog_argv = argv;
    setup_bup_main_module();
    prepend_lib_to_pythonpath(argv[0], "../lib");
    return bup_py_main (argc, argv);
}

#elif defined(BUP_DEV_BUP_EXEC)

int main(int argc, char **argv)
{
    assert(argc > 0);
    prog_argc = argc - 1;
    prog_argv = argv + 1;
    setup_bup_main_module();
    prepend_lib_to_pythonpath(argv[0], "../lib");
    if (argc == 1)
        return bup_py_main (1, argv);
    // This can't handle a script with a name like "-c", but that's
    // python's problem, not ours.
    return bup_py_main (2, argv);
}

#else // normal bup command

int main(int argc, char **argv)
{
    assert(argc > 0);
    prog_argc = argc;
    prog_argv = argv;
    setup_bup_main_module();
    prepend_lib_to_pythonpath(argv[0], "..");
    char *bup_argv[] = { argv[0], "-m", "bup.main" };
    return bup_py_main (3, bup_argv);
}

#endif // normal bup command
