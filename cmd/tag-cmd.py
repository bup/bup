#!/usr/bin/env python
"""Tag a commit in the bup repository.
Creating a tag on a commit can be used for avoiding automatic cleanup from
removing this commit due to old age.
"""
import sys
import os

from bup import git, options
from bup.helpers import *

# FIXME: review for safe writes.

handle_ctrl_c()

optspec = """
bup tag
bup tag [-f] <tag name> <commit>
bup tag -d [-f] <tag name>
--
d,delete=   Delete a tag
f,force     Overwrite existing tag, or ignore missing tag when deleting
"""

o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()

tags = [t for sublist in git.tags().values() for t in sublist]

if opt.delete:
    # git.delete_ref() doesn't complain if a ref doesn't exist.  We
    # could implement this verification but we'd need to read in the
    # contents of the tag file and pass the hash, and we already know
    # about the tag's existance via "tags".
    if not opt.force and opt.delete not in tags:
        log("error: tag '%s' doesn't exist\n" % opt.delete)
        sys.exit(1)
    tag_file = 'refs/tags/%s' % opt.delete
    git.delete_ref(tag_file)
    sys.exit(0)

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

if tag_name in tags and not opt.force:
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
