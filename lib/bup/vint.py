"""Binary encodings for bup."""

# Copyright (C) 2010 Rob Browning
#
# This code is covered under the terms of the GNU Library General
# Public License as described in the bup LICENSE file.

# Variable length integers are encoded as vints -- see lucene.

from base64 import b64decode, b64encode
from io import BytesIO
import json

from bup import _helpers


def write_vuint(port, x):
    port.write(encode_vuint(x))


def encode_vuint(x):
    try:
        return _helpers.vuint_encode(x)
    except OverflowError:
        if x < 0:
            raise ValueError(f'cannot encode negative value {x}') from None
    assert x != 0, 'the C code did not handle zero'
    ret = b''
    while True:
        seven_bits = x & 0x7f
        x >>= 7
        if x:
            ret += (0x80 | seven_bits).to_bytes(1, 'big')
        else:
            ret += seven_bits.to_bytes(1, 'big')
            break
    return ret


def read_vuint(port):
    c = port.read(1)
    if not c:
        return None
    assert isinstance(c, bytes)
    if ord(c) == 0:
        return 0
    result = 0
    offset = 0
    while True:
        b = ord(c)
        if b & 0x80:
            result |= ((b & 0x7f) << offset)
            offset += 7
            c = port.read(1)
            if not c:
                raise EOFError('encountered EOF while reading vuint')
        else:
            result |= (b << offset)
            break
    return result


def write_vint(port, x):
    # Sign is handled with the second bit of the first byte.  All else
    # matches vuint.
    port.write(encode_vint(x))


def encode_vint(x):
    try:
        return _helpers.vint_encode(x)
    except OverflowError:
        pass
    assert x != 0, 'the C code did not handle zero'
    if x < 0:
        x = -x
        sign_and_six_bits = (x & 0x3f) | 0x40
    else:
        sign_and_six_bits = x & 0x3f
    x >>= 6
    assert x != 0, f'the C code did not handle the small value {x}'
    return (0x80 | sign_and_six_bits).to_bytes(1, 'big') + encode_vuint(x)


def read_vint(port):
    c = port.read(1)
    if not c:
        return None
    assert isinstance(c, bytes)
    negative = False
    result = 0
    offset = 0
    # Handle first byte with sign bit specially.
    b = ord(c)
    if b & 0x40:
        negative = True
    result |= (b & 0x3f)
    if b & 0x80:
        offset += 6
        c = port.read(1)
        if not c:
            raise EOFError('encountered EOF while reading vint')
    elif negative:
        return -result
    else:
        return result
    while True:
        b = ord(c)
        if b & 0x80:
            result |= ((b & 0x7f) << offset)
            offset += 7
            c = port.read(1)
            if not c:
                raise EOFError('encountered EOF while reading vint')
        else:
            result |= (b << offset)
            break
    if negative:
        return -result
    return result


def write_bvec(port, x):
    write_vuint(port, len(x))
    port.write(x)


def read_bvec(port):
    n = read_vuint(port)
    if n is None:
        return None
    val = port.read(n)
    if len(val) != n: # e.g. EOF when n != 0
        raise EOFError('EOF while reading bvec bytes')
    return val


def encode_bvec(x):
    return _helpers.vuint_encode(len(x)) + x


def skip_bvec(port):
    n = read_vuint(port)
    if n is None:
        raise EOFError('encountered EOF while skipping bvec')
    val = port.read(n)
    if not val:
        raise EOFError('encountered EOF while skipping bvec')


def _tree_needs_preprocessing(x):
    """Return true if we're going to need to change anything in x
    before JSON encoding it."""
    # Consider _json_for_tree when making changes
    if isinstance(x, (str, int, bool, float)):
        return False
    if isinstance(x, bytes):
        return True
    if isinstance(x, (list, tuple)):
        if not x:
            return False
        if isinstance(x[0], str) and x[0] and x[0][0] in ('?', '!'):
            return True
        for item in x:
            if _tree_needs_preprocessing(item):
                return True
        return False
    if isinstance(x, dict):
        for k, v in x.items():
            assert isinstance(k, str), f'dict key {k} is not a string in {x}'
            if _tree_needs_preprocessing(v):
                return True
        return False
    raise ValueError(f'Cannot currently encode/decode {x!r}')


# The "tree" encoding transports heterogeneous trees of (currently)
# bool, int, float, string, bytes, list, tuple, dict via encoding as
# JSON.  This is arranged by reserving a JSON [TAG, DATA...] where the
# TAG is a string that starts with "?" for type extensions.  The only
# valid TAG right now is "?", which is used to encode bytes values as
# ["?", base-64-encoded-string].  In addition a TAG starting with "!"
# indicates that the original data happended to have a vector
# containing an initial string that started with "!" or "?".  This
# makes it possible to avoid interpreting that value as a tag, and to
# just recover the original data.  The chars "!?" were chosen as
# hopefully unlikely leading characters.
#
# For example:
#   encode:
#     b'foo' -> ["?","zcMv"]
#     ["?...1", ...2] -> ["!?...1", ...2]
#     ["!...1", ...2] -> ["!!...1", ...2]
#   decode:
#     ["?", "zcMv"] -> b'foo'
#     ["?"]  ["?"] -> b''
#     ["?" ""] -> b''
#     ["?type", ...] -> unknown_type or instance decoded via ...
#     ["!?foo"] -> ["?foo"]
#     ["!!foo"] -> ["!foo"]


def _json_for_tree(x):
    # Consider _tree_needs_preprocessing when making changes
    if isinstance(x, (str, int, bool, float)):
        return x
    if isinstance(x, bytes):
        if not x:
            return ['?']
        return ['?', b64encode(x).decode('ascii')]
    if isinstance(x, (list, tuple)):
        if not x:
            return x
        if isinstance(x[0], str) and x[0] and x[0][0] in ('?', '!'):
            result = ['!' + x[0]]
            result.extend(_json_for_tree(item) for item in x[1:])
            return result
        return [_json_for_tree(item) for item in x]
    if isinstance(x, dict):
        return {k: _json_for_tree(v) for k, v in x.items()}
    raise ValueError(f'Cannot currently encode {x!r} as JSON')


unrecognized_type = object()
_keep = object()

def _convert_json_to_tree(x):
    """Convert the JSON compatible x to a tree, decoding anything
    encoded.  This will destructively modify x if needed.  Return
    either the decoding of x, if needed, or _keep, if x is not
    encoded.  At the moment, it converts any tuples to lists, so you
    can always assume decoded tree sequences are lists.

    """
    def convert_seq(s):
        if not isinstance(s[0], str):
            for i, item in enumerate(s):
                if (new := _convert_json_to_tree(item)) != _keep:
                    s[i] = new
            return _keep
        if s[0].startswith('!'): # (aliasing) drop ! from first item
            s[0] = s[0][1:]
            for i, item in enumerate(s, start=1):
                if (new := _convert_json_to_tree(item)) != _keep:
                    s[i] = new
            return _keep
        if not x[0].startswith('?'):
            return _keep
        tag = x[0]
        if len(tag) > 1:
            return unrecognized_type
        if len(x) == 1:
            return b''
        if len(x) != 2:
            raise ValueError(f'Improper bytes encoding: {x!r}')
        return b64decode(x[1])

    if isinstance(x, (str, int, bool, float)):
        return _keep
    if isinstance(x, list):
        if not x:
            return _keep
        return convert_seq(x)
    if isinstance(x, tuple): # json.load*, at least, won't produce a tuple
        if not x:
            return []
        return convert_seq(x)
    if isinstance(x, dict):
        # We ignore keys for now; python will reject bytes
        for k, v in x.items():
            if (new := _convert_json_to_tree(v)) != _keep:
                x[k] = new
        return _keep
    raise ValueError(f'Cannot currently decode {x!r} from JSON')


def encode_tree(x):
    """Encode a tree of dict, list, tuple, bool, int, float, bytes
    (with JSON as the underlying transport)."""
    # Currently does not support generators because we traverse the
    # data more than once.
    needs_preenc = _tree_needs_preprocessing(x)
    preenc = _json_for_tree(x) if needs_preenc else x
    return encode_bvec(json.dumps(preenc,  ensure_ascii=False).encode('utf-8'))


def write_tree(port, x):
    port.write(encode_tree(x))


def read_tree(port):
    """Decode a tree of dict, list, tuple, bool, int, float, bytes,
    etc. (with JSON as the underlying transport).  The result will
    have the unrecognized_type value where the incoming type isn't
    recognized (i.e. from newer sender).

    """
    bv = read_bvec(port)
    if not bv:
        raise EOFError('encountered EOF while reading tree')
    val = json.loads(bv.decode('utf-8'))
    if (new := _convert_json_to_tree(val)) != _keep:
        return new
    return val


def send(port, types, *args):
    if len(types) != len(args):
        raise ValueError('number of arguments does not match format string')
    for (type, value) in zip(types, args):
        if type == 'V':
            write_vuint(port, value)
        elif type == 'v':
            write_vint(port, value)
        elif type == 's':
            write_bvec(port, value)
        elif type == 't':
            write_tree(port, value)
        else:
            raise ValueError(f'unknown format string item {type!r}')


def recv(port, types):
    result = []
    for type in types:
        if type == 'V': decode = read_vuint
        elif type == 'v': decode = read_vint
        elif type == 's': decode = read_bvec
        elif type == 't': decode = read_tree
        else: raise ValueError(f'unknown format string item {type!r}')
        x = decode(port)
        if x is None:
            raise EOFError(f'EOF while reading type {type!r}')
        result.append(x)
    return result


def pack(types, *args):
    if 't' not in types:
        try:
            return _helpers.limited_vint_pack(types, args)
        except OverflowError:
            pass
    assert len(types) == len(args)
    ret = []
    for typ, value in zip(types, args):
        if typ == 'V':
            ret.append(encode_vuint(value))
        elif typ == 'v':
            ret.append(encode_vint(value))
        elif typ == 's':
            ret.append(encode_bvec(value))
        elif typ == 't':
            ret.append(encode_tree(value))
        else:
            raise ValueError(f'unknown format string item {typ!r}')
    return b''.join(ret)


def unpack(types, data):
    port = BytesIO(data)
    return recv(port, types)
