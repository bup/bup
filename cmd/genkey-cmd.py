#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import sys

try:
    import libnacl.public
    import libnacl.secret
except ImportError:
    print("libnacl not found, cannot generate keys")
    sys.exit(2)

pair = libnacl.public.SecretKey()
box = libnacl.secret.SecretBox()

print('[bup]')
print('  type = encrypted')
print('  storage = TBD')
print('  cachedir = TBD')
print('  repokey = ' + box.hex_sk().decode('ascii'))
print('  readkey = ' + pair.hex_sk().decode('ascii'))
print('  writekey = ' + pair.hex_pk().decode('ascii'))
