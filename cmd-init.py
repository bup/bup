#!/usr/bin/env python
import git, options, client
from helpers import *

optspec = """
[BUP_DIR=...] bup init [-r host:path]
--
r,remote=  remote repository path
"""
o = options.Options('bup init', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    log("bup init: no arguments expected\n")
    o.usage()


if opt.remote:
    git.init_repo()  # local repo
    git.check_repo_or_die()
    cli = client.Client(opt.remote, create=True)
    cli.close()
else:
    git.init_repo()
