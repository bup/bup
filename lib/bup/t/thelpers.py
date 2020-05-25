
from __future__ import absolute_import
from time import tzset
import helpers, math, os, re, subprocess

from wvtest import *

from bup.compat import bytes_from_byte, bytes_from_uint, environ
from bup.helpers import (atomically_replaced_file, batchpipe, detect_fakeroot,
                         grafted_path_components, mkdirp, parse_num,
                         path_components, readpipe, stripped_path_components,
                         shstr,
                         utc_offset_str)
from buptest import no_lingering_errors, test_tempdir
import bup._helpers as _helpers


bup_tmp = os.path.realpath(b'../../../t/tmp')
mkdirp(bup_tmp)


@wvtest
def test_parse_num():
    with no_lingering_errors():
        pn = parse_num
        WVPASSEQ(pn(b'1'), 1)
        WVPASSEQ(pn('1'), 1)
        WVPASSEQ(pn('0'), 0)
        WVPASSEQ(pn('1.5k'), 1536)
        WVPASSEQ(pn('2 gb'), 2*1024*1024*1024)
        WVPASSEQ(pn('1e+9 k'), 1000000000 * 1024)
        WVPASSEQ(pn('-3e-3mb'), int(-0.003 * 1024 * 1024))

@wvtest
def test_detect_fakeroot():
    with no_lingering_errors():
        if b'FAKEROOTKEY' in environ:
            WVPASS(detect_fakeroot())
        else:
            WVPASS(not detect_fakeroot())

@wvtest
def test_path_components():
    with no_lingering_errors():
        WVPASSEQ(path_components(b'/'), [(b'', b'/')])
        WVPASSEQ(path_components(b'/foo'), [(b'', b'/'), (b'foo', b'/foo')])
        WVPASSEQ(path_components(b'/foo/'), [(b'', b'/'), (b'foo', b'/foo')])
        WVPASSEQ(path_components(b'/foo/bar'),
                 [(b'', b'/'), (b'foo', b'/foo'), (b'bar', b'/foo/bar')])
        WVEXCEPT(Exception, path_components, b'foo')


@wvtest
def test_stripped_path_components():
    with no_lingering_errors():
        WVPASSEQ(stripped_path_components(b'/', []), [(b'', b'/')])
        WVPASSEQ(stripped_path_components(b'/', [b'']), [(b'', b'/')])
        WVPASSEQ(stripped_path_components(b'/', [b'/']), [(b'', b'/')])
        WVPASSEQ(stripped_path_components(b'/foo', [b'/']),
                 [(b'', b'/'), (b'foo', b'/foo')])
        WVPASSEQ(stripped_path_components(b'/', [b'/foo']), [(b'', b'/')])
        WVPASSEQ(stripped_path_components(b'/foo', [b'/bar']),
                 [(b'', b'/'), (b'foo', b'/foo')])
        WVPASSEQ(stripped_path_components(b'/foo', [b'/foo']), [(b'', b'/foo')])
        WVPASSEQ(stripped_path_components(b'/foo/bar', [b'/foo']),
                 [(b'', b'/foo'), (b'bar', b'/foo/bar')])
        WVPASSEQ(stripped_path_components(b'/foo/bar', [b'/bar', b'/foo', b'/baz']),
                 [(b'', b'/foo'), (b'bar', b'/foo/bar')])
        WVPASSEQ(stripped_path_components(b'/foo/bar/baz', [b'/foo/bar/baz']),
                 [(b'', b'/foo/bar/baz')])
        WVEXCEPT(Exception, stripped_path_components, b'foo', [])


@wvtest
def test_grafted_path_components():
    with no_lingering_errors():
        WVPASSEQ(grafted_path_components([(b'/chroot', b'/')], b'/foo'),
                 [(b'', b'/'), (b'foo', b'/foo')])
        WVPASSEQ(grafted_path_components([(b'/foo/bar', b'/')],
                                         b'/foo/bar/baz/bax'),
                 [(b'', b'/foo/bar'),
                  (b'baz', b'/foo/bar/baz'),
                  (b'bax', b'/foo/bar/baz/bax')])
        WVPASSEQ(grafted_path_components([(b'/foo/bar/baz', b'/bax')],
                                         b'/foo/bar/baz/1/2'),
                 [(b'', None),
                  (b'bax', b'/foo/bar/baz'),
                  (b'1', b'/foo/bar/baz/1'),
                  (b'2', b'/foo/bar/baz/1/2')])
        WVPASSEQ(grafted_path_components([(b'/foo', b'/bar/baz/bax')],
                                         b'/foo/bar'),
                 [(b'', None),
                  (b'bar', None),
                  (b'baz', None),
                  (b'bax', b'/foo'),
                  (b'bar', b'/foo/bar')])
        WVPASSEQ(grafted_path_components([(b'/foo/bar/baz', b'/a/b/c')],
                                         b'/foo/bar/baz'),
                 [(b'', None), (b'a', None), (b'b', None), (b'c', b'/foo/bar/baz')])
        WVPASSEQ(grafted_path_components([(b'/', b'/a/b/c/')], b'/foo/bar'),
                 [(b'', None), (b'a', None), (b'b', None), (b'c', b'/'),
                  (b'foo', b'/foo'), (b'bar', b'/foo/bar')])
        WVEXCEPT(Exception, grafted_path_components, b'foo', [])


@wvtest
def test_shstr():
    with no_lingering_errors():
        # Do nothing for strings and bytes
        WVPASSEQ(shstr(b''), b'')
        WVPASSEQ(shstr(b'1'), b'1')
        WVPASSEQ(shstr(b'1 2'), b'1 2')
        WVPASSEQ(shstr(b"1'2"), b"1'2")
        WVPASSEQ(shstr(''), '')
        WVPASSEQ(shstr('1'), '1')
        WVPASSEQ(shstr('1 2'), '1 2')
        WVPASSEQ(shstr("1'2"), "1'2")

        # Escape parts of sequences
        WVPASSEQ(shstr((b'1 2', b'3')), b"'1 2' 3")
        WVPASSEQ(shstr((b"1'2", b'3')), b"'1'\"'\"'2' 3")
        WVPASSEQ(shstr((b"'1", b'3')), b"''\"'\"'1' 3")
        WVPASSEQ(shstr(('1 2', '3')), "'1 2' 3")
        WVPASSEQ(shstr(("1'2", '3')), "'1'\"'\"'2' 3")
        WVPASSEQ(shstr(("'1", '3')), "''\"'\"'1' 3")


@wvtest
def test_readpipe():
    with no_lingering_errors():
        x = readpipe([b'echo', b'42'])
        WVPASSEQ(x, b'42\n')
        try:
            readpipe([b'bash', b'-c', b'exit 42'])
        except Exception as ex:
            rx = '^subprocess b?"bash -c \'exit 42\'" failed with status 42$'
            if not re.match(rx, str(ex)):
                WVPASSEQ(str(ex), rx)


@wvtest
def test_batchpipe():
    with no_lingering_errors():
        for chunk in batchpipe([b'echo'], []):
            WVPASS(False)
        out = b''
        for chunk in batchpipe([b'echo'], [b'42']):
            out += chunk
        WVPASSEQ(out, b'42\n')
        try:
            batchpipe([b'bash', b'-c'], [b'exit 42'])
        except Exception as ex:
            WVPASSEQ(str(ex),
                     "subprocess 'bash -c exit 42' failed with status 42")
        args = [str(x) for x in range(6)]
        # Force batchpipe to break the args into batches of 3.  This
        # approach assumes all args are the same length.
        arg_max = \
            helpers._argmax_base([b'echo']) + helpers._argmax_args_size(args[:3])
        batches = batchpipe(['echo'], args, arg_max=arg_max)
        WVPASSEQ(next(batches), b'0 1 2\n')
        WVPASSEQ(next(batches), b'3 4 5\n')
        WVPASSEQ(next(batches, None), None)
        batches = batchpipe([b'echo'], [str(x) for x in range(5)], arg_max=arg_max)
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


def set_tz(tz):
    if not tz:
        del environ[b'TZ']
    else:
        environ[b'TZ'] = tz
    tzset()


@wvtest
def test_utc_offset_str():
    with no_lingering_errors():
        tz = environ.get(b'TZ')
        tzset()
        try:
            set_tz(b'FOO+0:00')
            WVPASSEQ(utc_offset_str(0), b'+0000')
            set_tz(b'FOO+1:00')
            WVPASSEQ(utc_offset_str(0), b'-0100')
            set_tz(b'FOO-1:00')
            WVPASSEQ(utc_offset_str(0), b'+0100')
            set_tz(b'FOO+3:3')
            WVPASSEQ(utc_offset_str(0), b'-0303')
            set_tz(b'FOO-3:3')
            WVPASSEQ(utc_offset_str(0), b'+0303')
            # Offset is not an integer number of minutes
            set_tz(b'FOO+3:3:3')
            WVPASSEQ(utc_offset_str(1), b'-0303')
            set_tz(b'FOO-3:3:3')
            WVPASSEQ(utc_offset_str(1), b'+0303')
            WVPASSEQ(utc_offset_str(314159), b'+0303')
        finally:
            if tz:
                set_tz(tz)
            else:
                try:
                    set_tz(None)
                except KeyError:
                    pass

@wvtest
def test_valid_save_name():
    with no_lingering_errors():
        valid = helpers.valid_save_name
        WVPASS(valid(b'x'))
        WVPASS(valid(b'x@'))
        WVFAIL(valid(b'@'))
        WVFAIL(valid(b'/'))
        WVFAIL(valid(b'/foo'))
        WVFAIL(valid(b'foo/'))
        WVFAIL(valid(b'/foo/'))
        WVFAIL(valid(b'foo//bar'))
        WVFAIL(valid(b'.'))
        WVFAIL(valid(b'bar.'))
        WVFAIL(valid(b'foo@{'))
        for x in b' ~^:?*[\\':
            WVFAIL(valid(b'foo' + bytes_from_byte(x)))
        for i in range(20):
            WVFAIL(valid(b'foo' + bytes_from_uint(i)))
        WVFAIL(valid(b'foo' + bytes_from_uint(0x7f)))
        WVFAIL(valid(b'foo..bar'))
        WVFAIL(valid(b'bar.lock/baz'))
        WVFAIL(valid(b'foo/bar.lock/baz'))
        WVFAIL(valid(b'.bar/baz'))
        WVFAIL(valid(b'foo/.bar/baz'))
