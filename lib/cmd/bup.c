
#define PY_SSIZE_T_CLEAN
#define _GNU_SOURCE  1 // asprintf
#undef NDEBUG

// According to Python, its header has to go first:
//   http://docs.python.org/2/c-api/intro.html#include-files
//   http://docs.python.org/3/c-api/intro.html#include-files
#include <Python.h>

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

__attribute__ ((format(printf, 2, 3)))
static void
die(int exit_status, const char * const msg, ...)
{
    if (fputs("bup: ", stderr) == EOF)
        exit(3);
    va_list ap;
    va_start(ap, msg);;
    if (vfprintf(stderr, msg, ap) < 0)
        exit(3);
    va_end(ap);
    exit(exit_status);
}

static int prog_argc = 0;
static char **prog_argv = NULL;
static char *orig_env_pythonpath = NULL;

static PyObject*
get_argv(PyObject *self, PyObject *args)
{
    if (!PyArg_ParseTuple(args, ""))
	return NULL;

    PyObject *result = PyList_New(prog_argc);
    for (int i = 0; i < prog_argc; i++) {
        PyObject *s = PyBytes_FromString(prog_argv[i]);
        if (!s)
            die(2, "cannot convert argument to bytes: %s\n", prog_argv[i]);
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
            die(2, "cannot convert PYTHONPATH to bytes: %s\n",
                orig_env_pythonpath);
        PyObject_SetAttrString(mod, "env_pythonpath", py_p);
        Py_DECREF(py_p);
    }
    return 1;
}

#if PY_MAJOR_VERSION >= 3

static struct PyModuleDef bup_main_module_def = {
    .m_base = PyModuleDef_HEAD_INIT,
    .m_name = "bup_main",
    .m_doc = "Built-in bup module providing direct access to argv.",
    .m_size = -1,
    .m_methods = bup_main_methods
};

PyObject *
PyInit_bup_main(void) {
    PyObject *mod =  PyModule_Create(&bup_main_module_def);
    if (!setup_module(mod))
    {
        Py_DECREF(mod);
        return NULL;
    }
    return mod;
}

#else // PY_MAJOR_VERSION < 3

void PyInit_bup_main(void)
{
    PyObject *mod = Py_InitModule("bup_main", bup_main_methods);
    if (mod == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "bup._helpers init failed");
        return;
    }
    if (!setup_module(mod))
    {
        PyErr_SetString(PyExc_RuntimeError, "bup._helpers set up failed");
        Py_DECREF(mod);
        return;
    }
}

#endif // PY_MAJOR_VERSION < 3

static void
setup_bup_main_module(void) {

    char *path = getenv("PYTHONPATH");
    if (path)
        orig_env_pythonpath = strdup(path);

    if (PyImport_AppendInittab("bup_main", PyInit_bup_main) == -1)
        die(2, "unable to register bup_main module\n");
}

#if defined(__APPLE__) && defined(__MACH__)

static char *exe_parent_dir(const char * const argv_0) {
    char path[4096];  // FIXME
    uint32_t size = sizeof(path);
    if(_NSGetExecutablePath(path, &size) !=0)
        die(2, "unable to find executable path\n");
    char * abs_exe = realpath(path, NULL);
    if (!abs_exe)
        die(2, "cannot resolve path (%s): %s\n", strerror(errno), path);
    char * const abs_parent = strdup(dirname(abs_exe));
    assert(abs_parent);
    free(abs_exe);
    return abs_parent;
}

#elif defined(__FreeBSD__) || defined(__NetBSD__)

static char *exe_path ()
{
    const int mib[] = {CTL_KERN, KERN_PROC, KERN_PROC_PATHNAME, -1};
    size_t path_len;
    int rc = sysctl (mib, 4, NULL, &path_len, NULL, 0);
    if (rc != 0) die(2, "unable to determine executable path length\n");
    char *path = malloc (path_len);
    if (!path) die(2, "unable to allocate memory for executable path\n");
    rc = sysctl (mib, 4, path, &path_len, NULL, 0);
    if (rc != 0) die(2, "unable to determine executable path via sysctl\n");
    return path;
}

static char *exe_parent_dir(const char * const argv_0)
{
    char * const exe = exe_path();
    if (!exe) die(2, "unable to determine executable path\n");
    char * const parent = strdup(dirname(exe));
    if (!parent) die(2, "unable to determine parent directory of executable\n");
    free(exe);
    return parent;
}

#else // not defined(__FreeBSD__) || defined(__NetBSD__)

/// Use /proc if possible, and if all else fails, search in the PATH

#if defined(__linux__)
# define PROC_SELF_EXE "/proc/self/exe"
#elif defined(__sun) || defined (sun)
# define PROC_SELF_EXE "/proc/self/path/a.out"
#else
# define PROC_SELF_EXE NULL
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
                    die(2, "cannot stat %s: %s\n", candidate, strerror(errno));
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
                    die(2, "cannot determine executability of %s: %s\n",
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
    const char * const slash = index(argv_0, '/');
    if (slash) {
        candidate = strdup(argv_0);
        assert(candidate);
    } else {
        const char * const env_path = getenv("PATH");
        if (!env_path)
            die(2, "no PATH and executable isn't relative or absolute: %s\n",
                argv_0);
        char *path_exe = find_in_path(argv_0, env_path);
        if (path_exe) {
            char * abs_exe = realpath(path_exe, NULL);
            if (!abs_exe)
                die(2, "cannot resolve path (%s): %s\n",
                    strerror(errno), path_exe);
            free(path_exe);
            candidate = abs_exe;
        }
    }
    if (!candidate)
        return NULL;

    char * const abs_exe = realpath(candidate, NULL);
    if (!abs_exe)
        die(2, "cannot resolve path (%s): %s\n", strerror(errno), candidate);
    free(candidate);
    char * const abs_parent = strdup(dirname(abs_exe));
    assert(abs_parent);
    free(abs_exe);
    return abs_parent;
}

static char *exe_parent_dir(const char * const argv_0)
{
    if (PROC_SELF_EXE != NULL) {
        char path[4096];  // FIXME
        int len = readlink(PROC_SELF_EXE, path, sizeof(path));
        if (len == sizeof(path))
            die(2, "unable to resolve symlink %s: %s\n",
                PROC_SELF_EXE, strerror(errno));
        if (len != -1) {
            path[len] = '\0';
            return strdup(dirname(path));
        }
        switch (errno) {
            case ENOENT: case EACCES: case EINVAL: case ELOOP: case ENOTDIR:
            case ENAMETOOLONG:
                break;
            default:
                die(2, "cannot resolve %s: %s\n", path, strerror(errno));
                break;
        }
    }
    return find_exe_parent(argv_0);
}

#endif // use /proc if possible, and if all else fails, search in the PATh

static void
setenv_or_die(const char *name, const char *value)
{
    int rc = setenv(name, value, 1);
    if (rc != 0)
        die(2, "setenv %s=%s failed (%s)\n", name, value, strerror(errno));
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
        die(2, "unable find lib dir (%s): %s\n", strerror(errno), bupmodpath);
    if (!S_ISDIR(st.st_mode))
        die(2, "lib path is not dir: %s\n", bupmodpath);
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

#if PY_MAJOR_VERSION > 2
#define bup_py_main Py_BytesMain
# else
#define bup_py_main Py_Main
#endif

#if defined(BUP_DEV_BUP_PYTHON) && defined(BUP_DEV_BUP_EXEC)
# error "Both BUP_DEV_BUP_PYTHON and BUP_DEV_BUP_EXEC are defined"
#endif

#ifdef BUP_DEV_BUP_PYTHON

int main(int argc, char **argv)
{
    prog_argc = argc;
    prog_argv = argv;
    setup_bup_main_module();
    prepend_lib_to_pythonpath(argv[0], "../lib");
    return bup_py_main (argc, argv);
}

#elif defined(BUP_DEV_BUP_EXEC)

int main(int argc, char **argv)
{
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
    prog_argc = argc;
    prog_argv = argv;
    setup_bup_main_module();
    prepend_lib_to_pythonpath(argv[0], "..");
    char *bup_argv[] = { argv[0], "-m", "bup.main" };
    return bup_py_main (3, bup_argv);
}

#endif // normal bup command
