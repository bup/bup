#!/usr/bin/env python2.5
import git, options
from helpers import *

optspec = """
[BUP_DIR=...] bup init
"""
o = options.Options('bup init', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    log("bup init: no arguments expected\n")
    o.usage()

exit(git.init_repo())

