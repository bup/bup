#!/usr/bin/env python
"""Tag a commit in the bup repository.
Creating a tag on a commit can be used for avoiding automatic cleanup from
removing this commit due to old age.
"""
import sys
import os

from bup import git, options
from bup.helpers import *


handle_ctrl_c()

optspec = """
bup tag
bup tag <tag name> <commit>
bup tag -d <tag name>
--
d,delete=   Delete a tag
"""

o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()

if opt.delete:
    tag_file = git.repo('refs/tags/%s' % opt.delete)
    debug1("tag file: %s\n" % tag_file)
    if not os.path.exists(tag_file):
        log("bup: error: tag '%s' not found.\n" % opt.delete)
        sys.exit(1)

    try:
        os.unlink(tag_file)
    except OSError, e:
        log("bup: error: unable to delete tag '%s': %s" % (opt.delete, e))
        sys.exit(1)

    sys.exit(0)

tags = [t for sublist in git.tags().values() for t in sublist]

if not extra:
    for t in tags:
        print t
    sys.exit(0)
elif len(extra) < 2:
    o.fatal('no commit ref or hash given.')

(tag_name, commit) = extra[:2]
if not tag_name:
    o.fatal("tag name must not be empty.")
debug1("args: tag name = %s; commit = %s\n" % (tag_name, commit))

if tag_name in tags:
    log("bup: error: tag '%s' already exists\n" % tag_name)
    sys.exit(1)

if tag_name.startswith('.'):
    o.fatal("'%s' is not a valid tag name." % tag_name)

try:
    hash = git.rev_parse(commit)
except git.GitError, e:
    log("bup: error: %s" % e)
    sys.exit(2)

if not hash:
    log("bup: error: commit %s not found.\n" % commit)
    sys.exit(2)

pL = git.PackIdxList(git.repo('objects/pack'))
if not pL.exists(hash):
    log("bup: error: commit %s not found.\n" % commit)
    sys.exit(2)

tag_file = git.repo('refs/tags/%s' % tag_name)
try:
    tag = file(tag_file, 'w')
except OSError, e:
    log("bup: error: could not create tag '%s': %s" % (tag_name, e))
    sys.exit(3)

tag.write(hash.encode('hex'))
tag.close()
