
from wvpytest import *

from bup.io import enc_dsq, enc_sh


def test_enc_dsq():
    def enc_byte(b):
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

    def enc(bv):
        result = [b"$'"]
        for b in bv:
            result.append(enc_byte(b))
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

def test_enc_sh():
    assert br"''" == enc_sh(b'')
    assert br"'a|b'" == enc_sh(b'a|b')
    assert br"$'\n'" == enc_sh(b'\n')
    assert br"$'\''" == enc_sh(b"'")
    assert br"$'\x00'" == enc_sh(b'\0')
    for needs_dsq in range(32):
        assert enc_dsq(b'%c' % needs_dsq) == enc_sh(needs_dsq.to_bytes(1, 'big'))
    for needs_sq in br'|&;<>()$`\" *?[]^!#~=%{,}':
        assert b"'%c'" % needs_sq == enc_sh(needs_sq.to_bytes(1, 'big'))
