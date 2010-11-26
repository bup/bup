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

o = options.Options('bup tag', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()

if opt.delete:
    tag_file = git.repo('refs/tags/%s' % opt.delete)
    debug1("tag file: %s\n" % tag_file)
    if not os.path.exists(tag_file):
        log("bup: error: tag '%s' not found." % opt.delete)
        sys.exit(1)

    try:
        os.unlink(tag_file)
    except OSError, e:
        log("bup: error: unable to delete tag: %s" % e)
        sys.exit(1)

    sys.exit(0)

tags = []
for (t, dummy) in git.list_refs():
    if t.startswith('refs/tags/'):
        tags.append(t[10:])

if not extra:
    for t in tags:
        log("%s\n" % t)
    sys.exit(0)
elif len(extra) != 2:
    log('bup: error: no ref or hash given.')
    sys.exit(1)

tag_name = extra[0]
commit = extra[1]
debug1("from args: tag name = %s; commit = %s\n" % (tag_name, commit))

if tag_name in tags:
    log("bup: error: tag '%s' already exists" % tag_name)
    sys.exit(1)

hash = git.rev_parse(commit)
if not hash:
    log("bup: error: commit %s not found." % commit)
    sys.exit(2)

pL = git.PackIdxList(git.repo('objects/pack'))
if not pL.exists(hash):
    log("bup: error: commit %s not found." % commit)
    sys.exit(2)

tag_file = git.repo('refs/tags/%s' % tag_name)
try:
    tag = file(tag_file, 'w')
except OSError, e:
    log('bup: error: could not create tag %s: %s' % (tag_name, e))
    sys.exit(3)

tag.write(hash.encode('hex'))
tag.close()
