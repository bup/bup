#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import sys

from bup import options
from bup.io import byte_stream
from bup.server import BupProtocolServer, GitServerBackend
from bup.helpers import (Conn, debug2)


optspec = """
bup server
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal('no arguments expected')

debug2('bup server: reading from stdin.\n')
BupProtocolServer(Conn(byte_stream(sys.stdin), byte_stream(sys.stdout)),
                  GitServerBackend()).handle()
