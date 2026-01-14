
from wvpytest import *

from bup.io import enc_dsq, enc_dsqs, enc_sh, enc_shs, qsql_id, qsql_str


def _dsq_enc_byte(b):
    bb = bytes([b])
    sym = {b'\a': br'\a',
           b'\b': br'\b',
           b'\t': br'\t',
           b'\n': br'\n',
           b'\v': br'\v',
           b'\f': br'\f',
           b'\r': br'\r',
           b'\x1b': br'\e'}
    sub = sym.get(bb)
    if sub:
        return sub
    if bb == b"'":
        return br"\'"
    if bb == b'\\':
        return br'\\'
    if b >= 127 or b < 7 or (b > 13 and b < 27) or (b > 27 and b < 32):
        return br'\x%02x' % b
    return bb

def test_enc_dsq():
    def enc(bv):
        result = [b"$'"]
        for b in bv:
            result.append(_dsq_enc_byte(b))
        result.append(b"'")
        return b''.join(result)
    for i in range(1, 256):
        bi = bytes([i])
        wvpasseq(enc(bi), enc_dsq(bi))
        v = b'foo' + bi
        wvpasseq(enc(v), enc_dsq(v))
        v = bi + b'foo'
        wvpasseq(enc(v), enc_dsq(v))
        v = b'foo' + bi + b'bar'
        wvpasseq(enc(v), enc_dsq(v))

    assert br"$'x'" == enc_dsq(b'x')
    assert br"$'\n'" == enc_dsq(b'\n')
    assert br"$'\x03'" == enc_dsq(b'\x03')

def test_enc_dsqs():
    def enc(s):
        result = ["$'"]
        for c in s:
            result.append(_dsq_enc_byte(ord(c)).decode('ascii'))
        result.append("'")
        return ''.join(result)
    for i in range(1, 128):
        c = chr(i)
        wvpasseq(enc(c), enc_dsqs(c))
        v = 'foo' + c
        wvpasseq(enc(v), enc_dsqs(v))
        v = c + 'foo'
        wvpasseq(enc(v), enc_dsqs(v))
        v = 'foo' + c + 'bar'
        wvpasseq(enc(v), enc_dsqs(v))

    assert r"$'x'" == enc_dsqs('x')
    assert r"$'\n'" == enc_dsqs('\n')
    assert r"$'\x03'" == enc_dsqs('\x03')
    assert r"$'\x80'" \
        == enc_dsqs(b'\x80'.decode('ascii', errors='surrogateescape'))
    assert r"$'\xb5'" \
        == enc_dsqs(b'\xb5'.decode('utf-8', errors='surrogateescape'))

def test_enc_sh():
    assert br"''" == enc_sh(b'')
    assert br"'a|b'" == enc_sh(b'a|b')
    assert br"$'\n'" == enc_sh(b'\n')
    assert br"$'\''" == enc_sh(b"'")
    assert br"$'\x00'" == enc_sh(b'\0')
    assert br"$'\x7f'" == enc_sh(b'\x7f')
    for needs_dsq in range(32):
        assert enc_dsq(b'%c' % needs_dsq) == enc_sh(needs_dsq.to_bytes(1, 'big'))
    for needs_sq in br'|&;<>()$`\" *?[]^!#~=%{,}':
        assert b"'%c'" % needs_sq == enc_sh(needs_sq.to_bytes(1, 'big'))

def test_enc_shs():
    assert r"''" == enc_shs('')
    assert r"'a|b'" == enc_shs('a|b')
    assert r"$'\n'" == enc_shs('\n')
    assert r"$'\''" == enc_shs("'")
    assert r"$'\x00'" == enc_shs('\0')
    assert r"$'\x7f'" == enc_shs('\x7f')
    for needs_dsq in range(32):
        assert enc_dsqs(chr(needs_dsq)) == enc_shs(chr(needs_dsq))
    for needs_sq in r'|&;<>()$`\" *?[]^!#~=%{,}':
        assert f"'{needs_sq}'" == enc_shs(needs_sq)
    # Characters outside ascii are passed through.
    assert 'büp' == enc_shs('büp')
    # Undecodable bytes are \xNN escaped
    assert r"$'\x80'" \
        == enc_shs(b'\x80'.decode('ascii', errors='surrogateescape'))
    assert r"$'\xb5'" \
        == enc_shs(b'\xb5'.decode('utf-8', errors='surrogateescape'))

def test_qsql_id():
    assert '""""' == qsql_id('"')
    assert '"x"' == qsql_id('x')
    assert '"""x"' == qsql_id('"x')
    assert '"x"""' == qsql_id('x"')
    assert '"x"""' == qsql_id('x"')
    assert '"x""y"' == qsql_id('x"y')
    assert '"x""y""z"' == qsql_id('x"y"z')

def test_qsql_str():
    assert "''''" == qsql_str("'")
    assert "'x'" == qsql_str("x")
    assert "'''x'" == qsql_str("'x")
    assert "'x'''" == qsql_str("x'")
    assert "'x'''" == qsql_str("x'")
    assert "'x''y'" == qsql_str("x'y")
    assert "'x''y''z'" == qsql_str("x'y'z")
