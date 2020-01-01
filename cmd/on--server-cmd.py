#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import sys, os, struct

from bup import options, helpers, path
from bup.compat import environ, py_maj
from bup.io import byte_stream

optspec = """
bup on--server
--
    This command is run automatically by 'bup on'
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])
if extra:
    o.fatal('no arguments expected')

# get the subcommand's argv.
# Normally we could just pass this on the command line, but since we'll often
# be getting called on the other end of an ssh pipe, which tends to mangle
# argv (by sending it via the shell), this way is much safer.

stdin = byte_stream(sys.stdin)
buf = stdin.read(4)
sz = struct.unpack('!I', buf)[0]
assert(sz > 0)
assert(sz < 1000000)
buf = stdin.read(sz)
assert(len(buf) == sz)
argv = buf.split(b'\0')
argv[0] = path.exe()
argv = [argv[0], b'mux', b'--'] + argv


# stdin/stdout are supposedly connected to 'bup server' that the caller
# started for us (often on the other end of an ssh tunnel), so we don't want
# to misuse them.  Move them out of the way, then replace stdout with
# a pointer to stderr in case our subcommand wants to do something with it.
#
# It might be nice to do the same with stdin, but my experiments showed that
# ssh seems to make its child's stderr a readable-but-never-reads-anything
# socket.  They really should have used shutdown(SHUT_WR) on the other end
# of it, but probably didn't.  Anyway, it's too messy, so let's just make sure
# anyone reading from stdin is disappointed.
#
# (You can't just leave stdin/stdout "not open" by closing the file
# descriptors.  Then the next file that opens is automatically assigned 0 or 1,
# and people *trying* to read/write stdin/stdout get screwed.)
os.dup2(0, 3)
os.dup2(1, 4)
os.dup2(2, 1)
fd = os.open(os.devnull, os.O_RDONLY)
os.dup2(fd, 0)
os.close(fd)

environ[b'BUP_SERVER_REVERSE'] = helpers.hostname()
os.execvp(argv[0], argv)
sys.exit(99)
