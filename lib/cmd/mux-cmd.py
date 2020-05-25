#!/bin/sh
"""": # -*-python-*-
# https://sourceware.org/bugzilla/show_bug.cgi?id=26034
export "BUP_ARGV_0"="$0"
arg_i=1
for arg in "$@"; do
    export "BUP_ARGV_${arg_i}"="$arg"
    shift
    arg_i=$((arg_i + 1))
done
# Here to end of preamble replaced during install
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0"
"""
# end of bup preamble

from __future__ import absolute_import
import os, struct, subprocess, sys

sys.path[:0] = [os.path.dirname(os.path.realpath(__file__)) + '/..']

from bup import compat, options
from bup.helpers import debug1, debug2, mux
from bup.io import byte_stream

# Give the subcommand exclusive access to stdin.
orig_stdin = os.dup(0)
devnull = os.open(os.devnull, os.O_RDONLY)
os.dup2(devnull, 0)
os.close(devnull)

optspec = """
bup mux command [arguments...]
--
"""
o = options.Options(optspec)
opt, flags, extra = o.parse(compat.argv[1:])
if len(extra) < 1:
    o.fatal('command is required')

subcmd = extra

debug2('bup mux: starting %r\n' % (extra,))

outr, outw = os.pipe()
errr, errw = os.pipe()
def close_fds():
    os.close(outr)
    os.close(errr)

p = subprocess.Popen(subcmd, stdin=orig_stdin, stdout=outw, stderr=errw,
                     close_fds=False, preexec_fn=close_fds)
os.close(outw)
os.close(errw)
sys.stdout.flush()
out = byte_stream(sys.stdout)
out.write(b'BUPMUX')
out.flush()
mux(p, out.fileno(), outr, errr)
os.close(outr)
os.close(errr)
prv = p.wait()

if prv:
    debug1('%s exited with code %d\n' % (extra[0], prv))

debug1('bup mux: done\n')

sys.exit(prv)
