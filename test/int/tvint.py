
from __future__ import absolute_import
from io import BytesIO

from wvtest import *

from bup import vint
from buptest import no_lingering_errors


def encode_and_decode_vuint(x):
    f = BytesIO()
    vint.write_vuint(f, x)
    return vint.read_vuint(BytesIO(f.getvalue()))


@wvtest
def test_vuint():
    with no_lingering_errors():
        for x in (0, 1, 42, 128, 10**16):
            WVPASSEQ(encode_and_decode_vuint(x), x)
        WVEXCEPT(Exception, vint.write_vuint, BytesIO(), -1)
        WVEXCEPT(EOFError, vint.read_vuint, BytesIO())


def encode_and_decode_vint(x):
    f = BytesIO()
    vint.write_vint(f, x)
    return vint.read_vint(BytesIO(f.getvalue()))


@wvtest
def test_vint():
    with no_lingering_errors():
        values = (0, 1, 42, 64, 10**16)
        for x in values:
            WVPASSEQ(encode_and_decode_vint(x), x)
        for x in [-x for x in values]:
            WVPASSEQ(encode_and_decode_vint(x), x)
        WVEXCEPT(EOFError, vint.read_vint, BytesIO())
        WVEXCEPT(EOFError, vint.read_vint, BytesIO(b"\x80\x80"))


def encode_and_decode_bvec(x):
    f = BytesIO()
    vint.write_bvec(f, x)
    return vint.read_bvec(BytesIO(f.getvalue()))


@wvtest
def test_bvec():
    with no_lingering_errors():
        values = (b'', b'x', b'foo', b'\0', b'\0foo', b'foo\0bar\0')
        for x in values:
            WVPASSEQ(encode_and_decode_bvec(x), x)
        WVEXCEPT(EOFError, vint.read_bvec, BytesIO())
        outf = BytesIO()
        for x in (b'foo', b'bar', b'baz', b'bax'):
            vint.write_bvec(outf, x)
        inf = BytesIO(outf.getvalue())
        WVPASSEQ(vint.read_bvec(inf), b'foo')
        WVPASSEQ(vint.read_bvec(inf), b'bar')
        vint.skip_bvec(inf)
        WVPASSEQ(vint.read_bvec(inf), b'bax')


def pack_and_unpack(types, *values):
    data = vint.pack(types, *values)
    return vint.unpack(types, data)


@wvtest
def test_pack_and_unpack():
    with no_lingering_errors():
        tests = [('', []),
                 ('s', [b'foo']),
                 ('ss', [b'foo', b'bar']),
                 ('sV', [b'foo', 0]),
                 ('sv', [b'foo', -1]),
                 ('V', [0]),
                 ('Vs', [0, b'foo']),
                 ('VV', [0, 1]),
                 ('Vv', [0, -1]),
                 ('v', [0]),
                 ('vs', [0, b'foo']),
                 ('vV', [0, 1]),
                 ('vv', [0, -1])]
        for test in tests:
            (types, values) = test
            WVPASSEQ(pack_and_unpack(types, *values), values)
        WVEXCEPT(Exception, vint.pack, 's')
        WVEXCEPT(Exception, vint.pack, 's', 'foo', 'bar')
        WVEXCEPT(Exception, vint.pack, 'x', 1)
        WVEXCEPT(Exception, vint.unpack, 's', '')
        WVEXCEPT(Exception, vint.unpack, 'x', '')
