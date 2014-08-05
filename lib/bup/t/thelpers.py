import helpers
import math
import os
import os.path
import tempfile
import stat
import bup._helpers as _helpers
from bup.helpers import *
from wvtest import *

bup_tmp = os.path.realpath('../../../t/tmp')
mkdirp(bup_tmp)

@wvtest
def test_next():
    # Test whatever you end up with for next() after import '*'.
    WVPASSEQ(next(iter([]), None), None)
    x = iter([1])
    WVPASSEQ(next(x, None), 1)
    WVPASSEQ(next(x, None), None)
    x = iter([1])
    WVPASSEQ(next(x, 'x'), 1)
    WVPASSEQ(next(x, 'x'), 'x')
    WVEXCEPT(StopIteration, next, iter([]))
    x = iter([1])
    WVPASSEQ(next(x), 1)
    WVEXCEPT(StopIteration, next, x)


@wvtest
def test_fallback_next():
    global next
    orig = next
    next = helpers._fallback_next
    try:
        test_next()
    finally:
        next = orig


@wvtest
def test_parse_num():
    pn = parse_num
    WVPASSEQ(pn('1'), 1)
    WVPASSEQ(pn('0'), 0)
    WVPASSEQ(pn('1.5k'), 1536)
    WVPASSEQ(pn('2 gb'), 2*1024*1024*1024)
    WVPASSEQ(pn('1e+9 k'), 1000000000 * 1024)
    WVPASSEQ(pn('-3e-3mb'), int(-0.003 * 1024 * 1024))

@wvtest
def test_detect_fakeroot():
    if os.getenv('FAKEROOTKEY'):
        WVPASS(detect_fakeroot())
    else:
        WVPASS(not detect_fakeroot())

@wvtest
def test_path_components():
    WVPASSEQ(path_components('/'), [('', '/')])
    WVPASSEQ(path_components('/foo'), [('', '/'), ('foo', '/foo')])
    WVPASSEQ(path_components('/foo/'), [('', '/'), ('foo', '/foo')])
    WVPASSEQ(path_components('/foo/bar'),
             [('', '/'), ('foo', '/foo'), ('bar', '/foo/bar')])
    WVEXCEPT(Exception, path_components, 'foo')


@wvtest
def test_stripped_path_components():
    WVPASSEQ(stripped_path_components('/', []), [('', '/')])
    WVPASSEQ(stripped_path_components('/', ['']), [('', '/')])
    WVPASSEQ(stripped_path_components('/', ['/']), [('', '/')])
    WVPASSEQ(stripped_path_components('/', ['/foo']), [('', '/')])
    WVPASSEQ(stripped_path_components('/foo', ['/bar']),
             [('', '/'), ('foo', '/foo')])
    WVPASSEQ(stripped_path_components('/foo', ['/foo']), [('', '/foo')])
    WVPASSEQ(stripped_path_components('/foo/bar', ['/foo']),
             [('', '/foo'), ('bar', '/foo/bar')])
    WVPASSEQ(stripped_path_components('/foo/bar', ['/bar', '/foo', '/baz']),
             [('', '/foo'), ('bar', '/foo/bar')])
    WVPASSEQ(stripped_path_components('/foo/bar/baz', ['/foo/bar/baz']),
             [('', '/foo/bar/baz')])
    WVEXCEPT(Exception, stripped_path_components, 'foo', [])


@wvtest
def test_grafted_path_components():
    WVPASSEQ(grafted_path_components([('/chroot', '/')], '/foo'),
             [('', '/'), ('foo', '/foo')])
    WVPASSEQ(grafted_path_components([('/foo/bar', '/')], '/foo/bar/baz/bax'),
             [('', '/foo/bar'),
              ('baz', '/foo/bar/baz'),
              ('bax', '/foo/bar/baz/bax')])
    WVPASSEQ(grafted_path_components([('/foo/bar/baz', '/bax')],
                                     '/foo/bar/baz/1/2'),
             [('', None),
              ('bax', '/foo/bar/baz'),
              ('1', '/foo/bar/baz/1'),
              ('2', '/foo/bar/baz/1/2')])
    WVPASSEQ(grafted_path_components([('/foo', '/bar/baz/bax')],
                                     '/foo/bar'),
             [('', None),
              ('bar', None),
              ('baz', None),
              ('bax', '/foo'),
              ('bar', '/foo/bar')])
    WVPASSEQ(grafted_path_components([('/foo/bar/baz', '/a/b/c')],
                                     '/foo/bar/baz'),
             [('', None), ('a', None), ('b', None), ('c', '/foo/bar/baz')])
    WVPASSEQ(grafted_path_components([('/', '/a/b/c/')], '/foo/bar'),
             [('', None), ('a', None), ('b', None), ('c', '/'),
              ('foo', '/foo'), ('bar', '/foo/bar')])
    WVEXCEPT(Exception, grafted_path_components, 'foo', [])


@wvtest
def test_readpipe():
    x = readpipe(['echo', '42'])
    WVPASSEQ(x, '42\n')
    try:
        readpipe(['bash', '-c', 'exit 42'])
    except Exception, ex:
        WVPASSEQ(str(ex), "subprocess 'bash -c exit 42' failed with status 42")


@wvtest
def test_batchpipe():
    for chunk in batchpipe(['echo'], []):
        WVPASS(False)
    out = ''
    for chunk in batchpipe(['echo'], ['42']):
        out += chunk
    WVPASSEQ(out, '42\n')
    try:
        batchpipe(['bash', '-c'], ['exit 42'])
    except Exception, ex:
        WVPASSEQ(str(ex), "subprocess 'bash -c exit 42' failed with status 42")
    args = [str(x) for x in range(6)]
    # Force batchpipe to break the args into batches of 3.  This
    # approach assumes all args are the same length.
    arg_max = \
        helpers._argmax_base(['echo']) + helpers._argmax_args_size(args[:3])
    batches = batchpipe(['echo'], args, arg_max=arg_max)
    WVPASSEQ(next(batches), '0 1 2\n')
    WVPASSEQ(next(batches), '3 4 5\n')
    WVPASSEQ(next(batches, None), None)
    batches = batchpipe(['echo'], [str(x) for x in range(5)], arg_max=arg_max)
    WVPASSEQ(next(batches), '0 1 2\n')
    WVPASSEQ(next(batches), '3 4\n')
    WVPASSEQ(next(batches, None), None)


@wvtest
def test_atomically_replaced_file():
    tmpdir = tempfile.mkdtemp(dir=bup_tmp, prefix='bup-thelper-')
    target_file = os.path.join(tmpdir, 'test-atomic-write')
    initial_failures = wvfailure_count()

    with atomically_replaced_file(target_file, mode='w') as f:
        f.write('asdf')
        WVPASSEQ(f.mode, 'w')
    f = open(target_file, 'r')
    WVPASSEQ(f.read(), 'asdf')

    with atomically_replaced_file(target_file, mode='wb') as f:
        f.write(os.urandom(20))
        WVPASSEQ(f.mode, 'wb')

    if wvfailure_count() == initial_failures:
        subprocess.call(['rm', '-rf', tmpdir])
