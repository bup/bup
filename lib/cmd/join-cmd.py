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
bup_python="$(dirname "$0")/../../config/bin/python" || exit $?
exec "$bup_python" "$0"
"""
# end of bup preamble

from __future__ import absolute_import

# Intentionally replace the dirname "$0" that python prepends
import os, sys
sys.path[0] = os.path.dirname(os.path.realpath(__file__)) + '/..'

from bup import compat, git, options
from bup.compat import argv_bytes
from bup.helpers import linereader, log
from bup.io import byte_stream
from bup.repo import LocalRepo, RemoteRepo


optspec = """
bup join [-r host:path] [refs or hashes...]
--
r,remote=  remote repository path
o=         output filename
"""
o = options.Options(optspec)
opt, flags, extra = o.parse(compat.argv[1:])
if opt.remote:
    opt.remote = argv_bytes(opt.remote)

git.check_repo_or_die()

stdin = byte_stream(sys.stdin)

if not extra:
    extra = linereader(stdin)

ret = 0
repo = RemoteRepo(opt.remote) if opt.remote else LocalRepo()

if opt.o:
    outfile = open(opt.o, 'wb')
else:
    sys.stdout.flush()
    outfile = byte_stream(sys.stdout)

for ref in [argv_bytes(x) for x in extra]:
    try:
        for blob in repo.join(ref):
            outfile.write(blob)
    except KeyError as e:
        outfile.flush()
        log('error: %s\n' % e)
        ret = 1

sys.exit(ret)
