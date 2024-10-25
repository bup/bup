"""Binary encodings for bup."""

# Copyright (C) 2010 Rob Browning
#
# This code is covered under the terms of the GNU Library General
# Public License as described in the bup LICENSE file.

# Variable length integers are encoded as vints -- see lucene.

from io import BytesIO

from bup import compat
from bup import _helpers


def write_vuint(port, x):
    port.write(encode_vuint(x))


def encode_vuint(x):
    try:
        return _helpers.vuint_encode(x)
    except OverflowError:
        ret = b''
        bytes_from_uint = compat.bytes_from_uint
        if x < 0:
            raise Exception("vuints must not be negative")
        assert x, "the C version should have picked this up"

        while True:
            seven_bits = x & 0x7f
            x >>= 7
            if x:
                ret += bytes_from_uint(0x80 | seven_bits)
            else:
                ret += bytes_from_uint(seven_bits)
                break
        return ret

def read_vuint(port):
    c = port.read(1)
    if not c:
        raise EOFError('encountered EOF while reading vuint')
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
        bytes_from_uint = compat.bytes_from_uint
        assert x != 0, "the C version should have picked this up"
        if x < 0:
            x = -x
            sign_and_six_bits = (x & 0x3f) | 0x40
        else:
            sign_and_six_bits = x & 0x3f
        x >>= 6
        assert x, "the C version should have picked this up"
        return bytes_from_uint(0x80 | sign_and_six_bits) + encode_vuint(x)


def read_vint(port):
    c = port.read(1)
    if not c:
        raise EOFError('encountered EOF while reading vint')
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
    else:
        return result


def write_bvec(port, x):
    write_vuint(port, len(x))
    port.write(x)


def read_bvec(port):
    n = read_vuint(port)
    return port.read(n)


def encode_bvec(x):
    return _helpers.vuint_encode(len(x)) + x


def skip_bvec(port):
    port.read(read_vuint(port))

def send(port, types, *args):
    if len(types) != len(args):
        raise Exception('number of arguments does not match format string')
    for (type, value) in zip(types, args):
        if type == 'V':
            write_vuint(port, value)
        elif type == 'v':
            write_vint(port, value)
        elif type == 's':
            write_bvec(port, value)
        else:
            raise Exception('unknown xpack format string item "' + type + '"')

def recv(port, types):
    result = []
    for type in types:
        if type == 'V':
            result.append(read_vuint(port))
        elif type == 'v':
            result.append(read_vint(port))
        elif type == 's':
            result.append(read_bvec(port))
        else:
            raise Exception('unknown xunpack format string item "' + type + '"')
    return result

def pack(types, *args):
    try:
        return _helpers.limited_vint_pack(types, args)
    except OverflowError:
        assert len(types) == len(args)
        ret = []
        for typ, value in zip(types, args):
            if typ == 'V':
                ret.append(encode_vuint(value))
            elif typ == 'v':
                ret.append(encode_vint(value))
            elif typ == 's':
                ret.append(encode_bvec(value))
            else:
                assert False
        return b''.join(ret)

def unpack(types, data):
    port = BytesIO(data)
    return recv(port, types)
