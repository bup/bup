#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import sys

from bup import git, options, client
from bup.helpers import log, saved_errors
from bup.compat import argv_bytes


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
except git.GitError as e:
    log("bup: error: could not init repository: %s" % e)
    sys.exit(1)

if opt.remote:
    git.check_repo_or_die()
    cli = client.Client(argv_bytes(opt.remote), create=True)
    cli.close()
