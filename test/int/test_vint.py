
from io import BytesIO
from itertools import combinations_with_replacement

from wvpytest import *

from bup import vint


def encode_and_decode_vuint(x):
    f = BytesIO()
    vint.write_vuint(f, x)
    return vint.read_vuint(BytesIO(f.getvalue()))


def test_vuint():
        for x in (0, 1, 42, 128, 10**16, 10**100):
            WVPASSEQ(encode_and_decode_vuint(x), x)
        WVEXCEPT(Exception, vint.write_vuint, BytesIO(), -1)
        assert vint.read_vuint(BytesIO()) is None
        WVEXCEPT(EOFError, vint.read_vuint, BytesIO(b'\x80'))
        WVEXCEPT(EOFError, vint.read_vuint, BytesIO(b'\x80\x80'))


def encode_and_decode_vint(x):
    f = BytesIO()
    vint.write_vint(f, x)
    return vint.read_vint(BytesIO(f.getvalue()))


def test_vint():
    values = (0, 1, 42, 64, 10**16, 10**100)
    for x in values:
        WVPASSEQ(encode_and_decode_vint(x), x)
    for x in [-x for x in values]:
        WVPASSEQ(encode_and_decode_vint(x), x)
    assert vint.read_vint(BytesIO()) is None
    WVEXCEPT(EOFError, vint.read_vint, BytesIO(b'\x80'))
    WVEXCEPT(EOFError, vint.read_vint, BytesIO(b'\x80\x80'))


def encode_and_decode_bvec(x):
    f = BytesIO()
    vint.write_bvec(f, x)
    return vint.read_bvec(BytesIO(f.getvalue()))


def test_bvec():
    values = (b'', b'x', b'foo', b'\0', b'\0foo', b'foo\0bar\0')
    for x in values:
        WVPASSEQ(encode_and_decode_bvec(x), x)
    assert vint.read_bvec(BytesIO()) is None
    assert b'' == vint.read_bvec(BytesIO(b'\x00'))
    WVEXCEPT(EOFError, vint.read_bvec, BytesIO(b'\x80'))
    WVEXCEPT(EOFError, vint.read_bvec, BytesIO(b'\x01'))
    outf = BytesIO()
    for x in (b'foo', b'bar', b'baz', b'bax'):
        vint.write_bvec(outf, x)
    inf = BytesIO(outf.getvalue())
    WVPASSEQ(vint.read_bvec(inf), b'foo')
    WVPASSEQ(vint.read_bvec(inf), b'bar')
    vint.skip_bvec(inf)
    WVPASSEQ(vint.read_bvec(inf), b'bax')
    WVEXCEPT(EOFError, vint.skip_bvec, BytesIO(b''))
    WVEXCEPT(EOFError, vint.skip_bvec, BytesIO(b'\x80'))
    WVEXCEPT(EOFError, vint.skip_bvec, BytesIO(b'\x01'))


def pack_and_unpack(types, *values):
    data = vint.pack(types, *values)
    return vint.unpack(types, data)


def test_pack_and_unpack():
    candidates = (('s', b''),
                  ('s', b'x'),
                  ('s', b'foo'),
                  ('s', b'foo' * 10),
                  ('v', -10**100),
                  ('v', -1),
                  ('v', 0),
                  ('v', 1),
                  ('v', -10**100),
                  ('V', 0),
                  ('V', 1),
                  ('V', 10**100))
    WVPASSEQ(pack_and_unpack(''), [])
    for f, v in candidates:
        WVPASSEQ(pack_and_unpack(f, v), [v])
    for (f1, v1), (f2, v2) in combinations_with_replacement(candidates, r=2):
        WVPASSEQ(pack_and_unpack(f1 + f2, v1, v2), [v1, v2])
    WVEXCEPT(Exception, vint.pack, 's')
    WVEXCEPT(Exception, vint.pack, 's', 'foo', 'bar')
    WVEXCEPT(Exception, vint.pack, 'x', 1)
    WVEXCEPT(Exception, vint.unpack, 's', '')
    WVEXCEPT(Exception, vint.unpack, 'x', '')
