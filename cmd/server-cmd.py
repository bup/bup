#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import sys

from bup import options, git
from bup.io import byte_stream
from bup.protocol import BupProtocolServer
from bup.repo import LocalRepo
from bup.helpers import (Conn, debug2)


optspec = """
bup server
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal('no arguments expected')

debug2('bup server: reading from stdin.\n')

class ServerRepo(LocalRepo):
    def __init__(self, repo_dir):
         git.check_repo_or_die(repo_dir)
         LocalRepo.__init__(self, repo_dir)

BupProtocolServer(Conn(byte_stream(sys.stdin), byte_stream(sys.stdout)),
                  ServerRepo).handle()
