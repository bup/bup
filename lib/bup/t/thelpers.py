
from __future__ import absolute_import
import helpers, math, os, os.path, stat, subprocess

from wvtest import *

from bup.compat import environ
from bup.helpers import (atomically_replaced_file, batchpipe, detect_fakeroot,
                         grafted_path_components, mkdirp, parse_num,
                         path_components, readpipe, stripped_path_components,
                         utc_offset_str)
from buptest import no_lingering_errors, test_tempdir
import bup._helpers as _helpers


bup_tmp = os.path.realpath('../../../t/tmp')
mkdirp(bup_tmp)


@wvtest
def test_parse_num():
    with no_lingering_errors():
        pn = parse_num
        WVPASSEQ(pn('1'), 1)
        WVPASSEQ(pn('0'), 0)
        WVPASSEQ(pn('1.5k'), 1536)
        WVPASSEQ(pn('2 gb'), 2*1024*1024*1024)
        WVPASSEQ(pn('1e+9 k'), 1000000000 * 1024)
        WVPASSEQ(pn('-3e-3mb'), int(-0.003 * 1024 * 1024))

@wvtest
def test_detect_fakeroot():
    with no_lingering_errors():
        if os.getenv('FAKEROOTKEY'):
            WVPASS(detect_fakeroot())
        else:
            WVPASS(not detect_fakeroot())

@wvtest
def test_path_components():
    with no_lingering_errors():
        WVPASSEQ(path_components('/'), [('', '/')])
        WVPASSEQ(path_components('/foo'), [('', '/'), ('foo', '/foo')])
        WVPASSEQ(path_components('/foo/'), [('', '/'), ('foo', '/foo')])
        WVPASSEQ(path_components('/foo/bar'),
                 [('', '/'), ('foo', '/foo'), ('bar', '/foo/bar')])
        WVEXCEPT(Exception, path_components, 'foo')


@wvtest
def test_stripped_path_components():
    with no_lingering_errors():
        WVPASSEQ(stripped_path_components('/', []), [('', '/')])
        WVPASSEQ(stripped_path_components('/', ['']), [('', '/')])
        WVPASSEQ(stripped_path_components('/', ['/']), [('', '/')])
        WVPASSEQ(stripped_path_components('/foo', ['/']),
                 [('', '/'), ('foo', '/foo')])
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
    with no_lingering_errors():
        WVPASSEQ(grafted_path_components([('/chroot', '/')], '/foo'),
                 [('', '/'), ('foo', '/foo')])
        WVPASSEQ(grafted_path_components([('/foo/bar', '/')],
                                         '/foo/bar/baz/bax'),
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
    with no_lingering_errors():
        x = readpipe(['echo', '42'])
        WVPASSEQ(x, b'42\n')
        try:
            readpipe(['bash', '-c', 'exit 42'])
        except Exception as ex:
            WVPASSEQ(str(ex),
                     "subprocess 'bash -c exit 42' failed with status 42")


@wvtest
def test_batchpipe():
    with no_lingering_errors():
        for chunk in batchpipe(['echo'], []):
            WVPASS(False)
        out = b''
        for chunk in batchpipe(['echo'], ['42']):
            out += chunk
        WVPASSEQ(out, b'42\n')
        try:
            batchpipe(['bash', '-c'], ['exit 42'])
        except Exception as ex:
            WVPASSEQ(str(ex),
                     "subprocess 'bash -c exit 42' failed with status 42")
        args = [str(x) for x in range(6)]
        # Force batchpipe to break the args into batches of 3.  This
        # approach assumes all args are the same length.
        arg_max = \
            helpers._argmax_base(['echo']) + helpers._argmax_args_size(args[:3])
        batches = batchpipe(['echo'], args, arg_max=arg_max)
        WVPASSEQ(next(batches), b'0 1 2\n')
        WVPASSEQ(next(batches), b'3 4 5\n')
        WVPASSEQ(next(batches, None), None)
        batches = batchpipe(['echo'], [str(x) for x in range(5)], arg_max=arg_max)
        WVPASSEQ(next(batches), b'0 1 2\n')
        WVPASSEQ(next(batches), b'3 4\n')
        WVPASSEQ(next(batches, None), None)


@wvtest
def test_atomically_replaced_file():
    with no_lingering_errors():
        with test_tempdir(b'bup-thelper-') as tmpdir:
            target_file = os.path.join(tmpdir, b'test-atomic-write')

            with atomically_replaced_file(target_file, mode='w') as f:
                f.write('asdf')
                WVPASSEQ(f.mode, 'w')
            f = open(target_file, 'r')
            WVPASSEQ(f.read(), 'asdf')

            try:
                with atomically_replaced_file(target_file, mode='w') as f:
                    f.write('wxyz')
                    raise Exception()
            except:
                pass
            with open(target_file) as f:
                WVPASSEQ(f.read(), 'asdf')

            with atomically_replaced_file(target_file, mode='wb') as f:
                f.write(os.urandom(20))
                WVPASSEQ(f.mode, 'wb')


@wvtest
def test_utc_offset_str():
    with no_lingering_errors():
        tz = environ.get(b'TZ')
        try:
            environ[b'TZ'] = b'FOO+0:00'
            WVPASSEQ(utc_offset_str(0), b'+0000')
            environ[b'TZ'] = b'FOO+1:00'
            WVPASSEQ(utc_offset_str(0), b'-0100')
            environ[b'TZ'] = b'FOO-1:00'
            WVPASSEQ(utc_offset_str(0), b'+0100')
            environ[b'TZ'] = b'FOO+3:3'
            WVPASSEQ(utc_offset_str(0), b'-0303')
            environ[b'TZ'] = b'FOO-3:3'
            WVPASSEQ(utc_offset_str(0), b'+0303')
            # Offset is not an integer number of minutes
            environ[b'TZ'] = b'FOO+3:3:3'
            WVPASSEQ(utc_offset_str(1), b'-0303')
            environ[b'TZ'] = b'FOO-3:3:3'
            WVPASSEQ(utc_offset_str(1), b'+0303')
            WVPASSEQ(utc_offset_str(314159), b'+0303')
        finally:
            if tz:
                environ[b'TZ'] = tz
            else:
                try:
                    del environ[b'TZ']
                except KeyError:
                    pass

@wvtest
def test_valid_save_name():
    with no_lingering_errors():
        valid = helpers.valid_save_name
        WVPASS(valid('x'))
        WVPASS(valid('x@'))
        WVFAIL(valid('@'))
        WVFAIL(valid('/'))
        WVFAIL(valid('/foo'))
        WVFAIL(valid('foo/'))
        WVFAIL(valid('/foo/'))
        WVFAIL(valid('foo//bar'))
        WVFAIL(valid('.'))
        WVFAIL(valid('bar.'))
        WVFAIL(valid('foo@{'))
        for x in ' ~^:?*[\\':
            WVFAIL(valid('foo' + x))
        for i in range(20):
            WVFAIL(valid('foo' + chr(i)))
        WVFAIL(valid('foo' + chr(0x7f)))
        WVFAIL(valid('foo..bar'))
        WVFAIL(valid('bar.lock/baz'))
        WVFAIL(valid('foo/bar.lock/baz'))
        WVFAIL(valid('.bar/baz'))
        WVFAIL(valid('foo/.bar/baz'))
