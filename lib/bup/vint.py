"""Binary encodings for bup."""

# Copyright (C) 2010 Rob Browning
#
# This code is covered under the terms of the GNU Library General
# Public License as described in the bup LICENSE file.

from cStringIO import StringIO

# Variable length integers are encoded as vints -- see jakarta lucene.

def write_vuint(port, x):
    if x < 0:
        raise Exception("vuints must not be negative")
    elif x == 0:
        port.write('\0')
    else:
        while x:
            seven_bits = x & 0x7f
            x >>= 7
            if x:
                port.write(chr(0x80 | seven_bits))
            else:
                port.write(chr(seven_bits))


def read_vuint(port):
    c = port.read(1)
    if c == '':
        raise EOFError('encountered EOF while reading vuint');
    result = 0
    offset = 0
    while c:
        b = ord(c)
        if b & 0x80:
            result |= ((b & 0x7f) << offset)
            offset += 7
            c = port.read(1)
        else:
            result |= (b << offset)
            break
    return result


def write_vint(port, x):
    # Sign is handled with the second bit of the first byte.  All else
    # matches vuint.
    if x == 0:
        port.write('\0')
    else:
        if x < 0:
            x = -x
            sign_and_six_bits = (x & 0x3f) | 0x40
        else:
            sign_and_six_bits = x & 0x3f
        x >>= 6
        if x:
            port.write(chr(0x80 | sign_and_six_bits))
            write_vuint(port, x)
        else:
            port.write(chr(sign_and_six_bits))


def read_vint(port):
    c = port.read(1)
    if c == '':
        raise EOFError('encountered EOF while reading vint');
    negative = False
    result = 0
    offset = 0
    # Handle first byte with sign bit specially.
    if c:
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
    while c:
        b = ord(c)
        if b & 0x80:
            result |= ((b & 0x7f) << offset)
            offset += 7
            c = port.read(1)
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


def skip_bvec(port):
    port.read(read_vuint(port))


def pack(types, *args):
    if len(types) != len(args):
        raise Exception('number of arguments does not match format string')
    port = StringIO()
    for (type, value) in zip(types, args):
        if type == 'V':
            write_vuint(port, value)
        elif type == 'v':
            write_vint(port, value)
        elif type == 's':
            write_bvec(port, value)
        else:
            raise Exception('unknown xpack format string item "' + type + '"')
    return port.getvalue()


def unpack(types, data):
    result = []
    port = StringIO(data)
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
