#!/usr/bin/env python
from bup import git, options, client
from bup.helpers import *

optspec = """
[BUP_DIR=...] bup init [-r host:path]
--
r,remote=  remote repository path
"""
o = options.Options('bup init', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal("no arguments expected")


if opt.remote:
    if opt.remote and opt.remote.find(":") == -1:
        o.fatal("--remote argument must contain a colon")
    git.init_repo()  # local repo
    git.check_repo_or_die()
    try:
        cli = client.Client(opt.remote, create=True)
    except client.ClientError:
        o.fatal("server exited unexpectedly; see errors above")
    cli.close()
else:
    git.init_repo()
