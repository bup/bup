#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

import sys

from bup import git, options
from bup.helpers import linereader, log
from bup.repo import LocalRepo, RemoteRepo


optspec = """
bup join [-r host:path] [refs or hashes...]
--
r,remote=  remote repository path
o=         output filename
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()

if not extra:
    extra = linereader(sys.stdin)

ret = 0
repo = RemoteRepo(opt.remote) if opt.remote else LocalRepo()

if opt.o:
    outfile = open(opt.o, 'wb')
else:
    outfile = sys.stdout

for ref in extra:
    try:
        for blob in repo.join(ref):
            outfile.write(blob)
    except KeyError as e:
        outfile.flush()
        log('error: %s\n' % e)
        ret = 1

sys.exit(ret)
