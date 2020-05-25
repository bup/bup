#!/bin/sh
"""": # -*-python-*-
# https://sourceware.org/bugzilla/show_bug.cgi?id=26034
export "BUP_ARGV_0"="$0"
arg_i=1
for arg in "$@"; do
    export "BUP_ARGV_${arg_i}"="$arg"
    shift
    arg_i=$((arg_i + 1))
done
# Here to end of preamble replaced during install
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0"
"""
# end of bup preamble

from __future__ import absolute_import
from binascii import hexlify
import os, sys

sys.path[:0] = [os.path.dirname(os.path.realpath(__file__)) + '/..']

from bup import compat, git, options
from bup.compat import argv_bytes
from bup.helpers import debug1, handle_ctrl_c, log
from bup.io import byte_stream, path_msg

# FIXME: review for safe writes.

handle_ctrl_c()

optspec = """
bup tag
bup tag [-f] <tag name> <commit>
bup tag [-f] -d <tag name>
--
d,delete=   Delete a tag
f,force     Overwrite existing tag, or ignore missing tag when deleting
"""

o = options.Options(optspec)
opt, flags, extra = o.parse(compat.argv[1:])

git.check_repo_or_die()

tags = [t for sublist in git.tags().values() for t in sublist]

if opt.delete:
    # git.delete_ref() doesn't complain if a ref doesn't exist.  We
    # could implement this verification but we'd need to read in the
    # contents of the tag file and pass the hash, and we already know
    # about the tag's existance via "tags".
    tag_name = argv_bytes(opt.delete)
    if not opt.force and tag_name not in tags:
        log("error: tag '%s' doesn't exist\n" % path_msg(tag_name))
        sys.exit(1)
    tag_file = b'refs/tags/%s' % tag_name
    git.delete_ref(tag_file)
    sys.exit(0)

if not extra:
    for t in tags:
        sys.stdout.flush()
        out = byte_stream(sys.stdout)
        out.write(t)
        out.write(b'\n')
    sys.exit(0)
elif len(extra) != 2:
    o.fatal('expected commit ref and hash')

tag_name, commit = map(argv_bytes, extra[:2])
if not tag_name:
    o.fatal("tag name must not be empty.")
debug1("args: tag name = %s; commit = %s\n"
       % (path_msg(tag_name), commit.decode('ascii')))

if tag_name in tags and not opt.force:
    log("bup: error: tag '%s' already exists\n" % path_msg(tag_name))
    sys.exit(1)

if tag_name.startswith(b'.'):
    o.fatal("'%s' is not a valid tag name." % path_msg(tag_name))

try:
    hash = git.rev_parse(commit)
except git.GitError as e:
    log("bup: error: %s" % e)
    sys.exit(2)

if not hash:
    log("bup: error: commit %s not found.\n" % commit.decode('ascii'))
    sys.exit(2)

pL = git.PackIdxList(git.repo(b'objects/pack'))
if not pL.exists(hash):
    log("bup: error: commit %s not found.\n" % commit.decode('ascii'))
    sys.exit(2)

tag_file = git.repo(b'refs/tags/' + tag_name)
try:
    tag = open(tag_file, 'wb')
except OSError as e:
    log("bup: error: could not create tag '%s': %s" % (path_msg(tag_name), e))
    sys.exit(3)
with tag as tag:
    tag.write(hexlify(hash))
    tag.write(b'\n')
