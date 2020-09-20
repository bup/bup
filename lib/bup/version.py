
from __future__ import absolute_import, print_function

from bup import source_info
try:
    import bup.checkout_info as checkout_info
except ModuleNotFoundError:
    checkout_info = None
    pass


if checkout_info:
    date = checkout_info.date.encode('ascii')
    commit = checkout_info.commit.encode('ascii')
    modified = checkout_info.modified
else:
    date = source_info.date.encode('ascii')
    commit = source_info.commit.encode('ascii')
    modified = source_info.modified
    assert not date.startswith(b'$Format')
    assert not commit.startswith(b'$Format')

# The ~ in a version is a Debian-style "always less than" marker:
# https://www.debian.org/doc/debian-policy/ch-controlfields.html#version
base_version = b'0.33~'

version = base_version
if version.endswith(b'~'):
    version += commit

if modified:
    version += b'+'
