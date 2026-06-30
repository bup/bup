
#define _LARGEFILE64_SOURCE 1
#define PY_SSIZE_T_CLEAN 1
#undef NDEBUG
#include "../config/config.h"

// According to Python, its header has to go first:
//   http://docs.python.org/3/c-api/intro.html#include-files
#include <Python.h>

#include <assert.h>
#include <limits.h>

#include "bup/pyutil.h"


static void
test_bup_longish_to_py()
{
    // Only test (unsigned) long long since that's what python offers,
    // e.g. there's currently no (u)intmax_t support.
    PyObject *ll_min_py = PyLong_FromLongLong(LLONG_MIN);
    PyObject *ll_max_py = PyLong_FromLongLong(LLONG_MAX);
    PyObject *ull_max_py = PyLong_FromUnsignedLongLong(ULLONG_MAX);
    assert (ll_min_py);
    assert (ll_max_py);
    assert (ull_max_py);

    PyObject *py = BUP_LONGISH_TO_PY(LLONG_MIN);
    assert(py);
    assert(PyObject_RichCompareBool(py, ll_min_py, Py_EQ));
    Py_DECREF(py);

    py = BUP_LONGISH_TO_PY(LLONG_MAX);
    assert(py);
    assert(PyObject_RichCompareBool(py, ll_max_py, Py_EQ));
    Py_DECREF(py);

    py = BUP_LONGISH_TO_PY(ULLONG_MAX);
    assert(py);
    assert(PyObject_RichCompareBool(py, ull_max_py, Py_EQ));
    Py_DECREF(py);

    Py_DECREF(ull_max_py);
    Py_DECREF(ll_max_py);
    Py_DECREF(ll_min_py);
    fprintf(stderr, "test-pyutil::%s OK\n", __func__);
}

static void
test_bup_integral_from_py(void)
{
    PyObject *zero = PyLong_FromLong(0);
    PyObject *one = PyLong_FromLong(1);
    PyObject *neg_one = PyLong_FromLong(-1);
    PyObject *ll_min = PyLong_FromLongLong(LLONG_MIN);
    PyObject *ll_max = PyLong_FromLongLong(LLONG_MAX);
    PyObject *ull_max = PyLong_FromUnsignedLongLong(ULLONG_MAX);
    assert (one);
    assert (neg_one);
    assert (ll_min);
    assert (ll_max);
    assert (ull_max);

    {
        PyObject *min = PyLong_FromLong(INT_MIN);
        PyObject *max = PyLong_FromLong(INT_MAX);
        PyObject *umax = PyLong_FromUnsignedLong(UINT_MAX);
        PyObject *under = PyNumber_Subtract(min, one);
        PyObject *over = PyNumber_Add(max, one);
        PyObject *uover = PyNumber_Add(umax, one);
        assert(min);
        assert(max);
        assert(umax);
        assert(under);
        assert(over);
        assert(uover);

        int i;
        assert(bup_int_from_py(&i, min, __func__));
        assert(i == INT_MIN);
        assert(bup_int_from_py(&i, max, __func__));
        assert(i == INT_MAX);
        assert(!bup_int_from_py(&i, under, __func__));
        assert(PyErr_Occurred() == PyExc_OverflowError);
        PyErr_Clear();
        assert(!bup_int_from_py(&i, over, __func__));
        assert(PyErr_Occurred() == PyExc_OverflowError);
        PyErr_Clear();
        if (sizeof(int) < sizeof(long long)) {
            assert(!bup_int_from_py(&i, ll_min, __func__));
            assert(PyErr_Occurred() == PyExc_OverflowError);
            PyErr_Clear();
            assert(!bup_int_from_py(&i, ll_max, __func__));
            assert(PyErr_Occurred() == PyExc_OverflowError);
            PyErr_Clear();
        }

        unsigned u;
        assert(bup_uint_from_py(&u, zero, __func__));
        assert(u == 0);
        assert(bup_uint_from_py(&u, umax, __func__));
        assert(u == UINT_MAX);
        assert(!bup_uint_from_py(&u, neg_one, __func__));
        assert(PyErr_Occurred() == PyExc_OverflowError);
        PyErr_Clear();
        assert(!bup_uint_from_py(&u, uover, __func__));
        assert(PyErr_Occurred() == PyExc_OverflowError);
        PyErr_Clear();
        if (sizeof(unsigned) < sizeof(unsigned long long)) {
            assert(!bup_uint_from_py(&u, ull_max, __func__));
            assert(PyErr_Occurred() == PyExc_OverflowError);
            PyErr_Clear();
        }

        Py_DECREF(uover);
        Py_DECREF(over);
        Py_DECREF(under);
        Py_DECREF(umax);
        Py_DECREF(max);
        Py_DECREF(min);
    }

    {
        PyObject *umax = PyLong_FromUnsignedLong(ULONG_MAX);
        PyObject *uover = PyNumber_Add(umax, one);
        assert(umax);
        assert(uover);

        unsigned long u;
        assert(bup_ulong_from_py(&u, zero, __func__));
        assert(u == 0);
        assert(bup_ulong_from_py(&u, umax, __func__));
        assert(u == ULONG_MAX);
        assert(!bup_ulong_from_py(&u, neg_one, __func__));
        assert(PyErr_Occurred() == PyExc_OverflowError);
        PyErr_Clear();
        assert(!bup_ulong_from_py(&u, uover, __func__));
        assert(PyErr_Occurred() == PyExc_OverflowError);
        PyErr_Clear();
        if (sizeof(unsigned long) < sizeof(unsigned long long)) {
            assert(!bup_ulong_from_py(&u, ull_max, __func__));
            assert(PyErr_Occurred() == PyExc_OverflowError);
            PyErr_Clear();
        }

        Py_DECREF(uover);
        Py_DECREF(umax);
    }

    {
        PyObject *umax = PyLong_FromUnsignedLongLong(ULLONG_MAX);
        PyObject *uover = PyNumber_Add(umax, one);
        assert(umax);
        assert(uover);

        unsigned long long u;
        assert(bup_ullong_from_py(&u, zero, __func__));
        assert(u == 0);
        assert(bup_ullong_from_py(&u, umax, __func__));
        assert(u == ULLONG_MAX);
        assert(!bup_ullong_from_py(&u, neg_one, __func__));
        assert(PyErr_Occurred() == PyExc_OverflowError);
        PyErr_Clear();
        assert(!bup_ullong_from_py(&u, uover, __func__));
        assert(PyErr_Occurred() == PyExc_OverflowError);
        PyErr_Clear();

        Py_DECREF(uover);
        Py_DECREF(umax);
    }

    Py_DECREF(ull_max);
    Py_DECREF(ll_max);
    Py_DECREF(ll_min);
    Py_DECREF(neg_one);
    Py_DECREF(one);
    Py_DECREF(zero);
    fprintf(stderr, "test-pyutil::%s OK\n", __func__);
}

static void
test_bup_assign_pylong_to_integral(void)
{
    PyObject *zero = PyLong_FromLong(0);
    PyObject *one = PyLong_FromLong(1);
    PyObject *neg_one = PyLong_FromLong(-1);
    assert (zero);
    assert (one);
    assert (neg_one);

    int overflow;
    {
        long long i;
        PyObject *min = PyLong_FromLongLong(LLONG_MIN);
        PyObject *max = PyLong_FromLongLong(LLONG_MAX);
        PyObject *under = PyNumber_Subtract(min, one);
        PyObject *over = PyNumber_Add(max, one);

        overflow = 0;
        assert(BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, min, &overflow));
        assert(i == LLONG_MIN);
        assert(!overflow);
        overflow = 0;
        assert(BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, max, &overflow));
        assert(i == LLONG_MAX);
        assert(!overflow);
        overflow = 0;
        assert(!BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, under, &overflow));
        assert(overflow);
        overflow = 0;
        assert(!BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, over, &overflow));
        assert(overflow);

        Py_DECREF(max);
        Py_DECREF(min);
        Py_DECREF(over);
        Py_DECREF(under);
    }
    {
        unsigned long long i;
        PyObject *max = PyLong_FromUnsignedLongLong(ULLONG_MAX);
        PyObject *over = PyNumber_Add(max, one);

        overflow = 0;
        assert(BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, zero, &overflow));
        assert(i == 0);
        assert(!overflow);
        overflow = 0;
        assert(BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, max, &overflow));
        assert(i == ULLONG_MAX);
        assert(!overflow);
        overflow = 0;
        assert(!BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, neg_one, &overflow));
        assert(overflow);
        overflow = 0;
        assert(!BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, over, &overflow));
        assert(overflow);

        Py_DECREF(over);
        Py_DECREF(max);
    }
    {
        assert(sizeof(short) < sizeof(long long));

        short i;
        PyObject *min = PyLong_FromLongLong(SHRT_MIN);
        PyObject *max = PyLong_FromLongLong(SHRT_MAX);
        PyObject *under = PyNumber_Subtract(min, one);
        PyObject *over = PyNumber_Add(max, one);

        overflow = 0;
        assert(BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, min, &overflow));
        assert(i == SHRT_MIN);
        assert(!overflow);
        overflow = 0;
        assert(BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, max, &overflow));
        assert(i == SHRT_MAX);
        assert(!overflow);
        overflow = 0;
        assert(!BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, under, &overflow));
        assert(overflow);
        overflow = 0;
        assert(!BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, over, &overflow));
        assert(overflow);

        Py_DECREF(max);
        Py_DECREF(min);
        Py_DECREF(over);
        Py_DECREF(under);
    }
    {
        assert(sizeof(unsigned short) < sizeof(unsigned long long));

        unsigned short i;
        PyObject *max = PyLong_FromUnsignedLongLong(USHRT_MAX);
        PyObject *over = PyNumber_Add(max, one);

        overflow = 0;
        assert(BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, zero, &overflow));
        assert(i == 0);
        assert(!overflow);
        overflow = 0;
        assert(BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, max, &overflow));
        assert(i == USHRT_MAX);
        assert(!overflow);
        overflow = 0;
        assert(!BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, neg_one, &overflow));
        assert(overflow);
        overflow = 0;
        assert(!BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, over, &overflow));
        assert(overflow);

        Py_DECREF(over);
        Py_DECREF(max);
    }

    {
        int i;
        unsigned u;

        overflow = 0;
        assert(!BUP_ASSIGN_PYLONG_TO_INTEGRAL(&i, Py_None, &overflow));
        assert(!overflow);
        assert(PyErr_Occurred());
        PyErr_Clear();
        overflow = 0;
        assert(!BUP_ASSIGN_PYLONG_TO_INTEGRAL(&u, Py_None, &overflow));
        assert(!overflow);
        assert(PyErr_Occurred());
        PyErr_Clear();
    }

    Py_DECREF(neg_one);
    Py_DECREF(one);
    Py_DECREF(zero);
    fprintf(stderr, "test-pyutil::%s OK\n", __func__);
}

static PyObject*
run(PyObject *self, PyObject *args)
{
    if (!PyArg_ParseTuple(args, ""))
	return NULL;

    test_bup_longish_to_py();
    test_bup_integral_from_py();
    test_bup_assign_pylong_to_integral();

    fprintf(stderr, "test-pyutil OK\n");
    Py_RETURN_NONE;
}

static PyMethodDef test_methods[] = {
    {"run", run, METH_VARARGS, "Run tests." },
    {NULL, NULL, 0, NULL}
};

static int setup_module(PyObject *mod)
{
    return 1;
}

static struct PyModuleDef bup_main_module_def = {
    .m_base = PyModuleDef_HEAD_INIT,
    .m_name = "bup_test",
    .m_doc = "bup test module",
    .m_size = -1,
    .m_methods = test_methods
};

static PyObject *
PyInit_bup_test(void) {
    PyObject *mod =  PyModule_Create(&bup_main_module_def);
    if (!setup_module(mod))
    {
        Py_DECREF(mod);
        return NULL;
    }
    return mod;
}

int
main(int argc, char **argv)
{
    assert(argc == 1);
    if (PyImport_AppendInittab("bup_test", PyInit_bup_test) == -1) {
        fprintf(stderr, "unable to register bup_test module\n");
        exit(2);
    }
    char *bup_argv[] = { argv[0], "-c", "import bup_test; bup_test.run()"};
    return Py_BytesMain (3, bup_argv);
}
