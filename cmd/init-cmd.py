#!/usr/bin/env python
import sys

from bup import git, options, client
from bup.helpers import *


optspec = """
[BUP_DIR=...] bup init [-r host:path]
--
r,remote=  remote repository path
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal("no arguments expected")


try:
    git.init_repo()  # local repo
except git.GitError, e:
    log("bup: error: could not init repository: %s" % e)
    sys.exit(1)

if opt.remote:
    git.check_repo_or_die()
    cli = client.Client(opt.remote, create=True)
    cli.close()
