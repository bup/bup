#!/usr/bin/env python
import sys
from bup import git, options, client
from bup.helpers import *


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

if opt.remote:
    cli = client.Client(opt.remote)
    cat = cli.cat
else:
    cp = git.CatPipe()
    cat = cp.join

if opt.o:
    outfile = open(opt.o, 'wb')
else:
    outfile = sys.stdout

for id in extra:
    try:
        for blob in cat(id):
            outfile.write(blob)
    except KeyError, e:
        outfile.flush()
        log('error: %s\n' % e)
        ret = 1

sys.exit(ret)
