#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import sys

from bup import git, options
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
(opt, flags, extra) = o.parse(sys.argv[1:])
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
