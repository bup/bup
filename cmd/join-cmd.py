#!/usr/bin/env python
import sys
from bup import git, options, client
from bup.helpers import *


optspec = """
bup join [-r host:path] [refs or hashes...]
--
r,remote=  remote repository path
"""
o = options.Options('bup join', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()

if not extra:
    extra = linereader(sys.stdin)

ret = 0

if opt.remote:
    if opt.remote and opt.remote.find(":") == -1:
        o.fatal("--remote argument must contain a colon")
    try:
        cli = client.Client(opt.remote)
    except client.ClientError:
        o.fatal("server exited unexpectedly; see errors above")
    cat = cli.cat
else:
    cp = git.CatPipe()
    cat = cp.join

for id in extra:
    try:
        for blob in cat(id):
            sys.stdout.write(blob)
    except KeyError, e:
        sys.stdout.flush()
        log('error: %s\n' % e)
        ret = 1

sys.exit(ret)
