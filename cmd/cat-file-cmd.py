#!/usr/bin/env python
import sys, stat
from bup import options, git, vfs
from bup.helpers import *

optspec = """
bup cat-file [--meta|--bupm] /branch/revision/[path]
--
meta        print the target's metadata entry (decoded then reencoded) to stdout
bupm        print the target directory's .bupm file directly to stdout
"""

handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()
top = vfs.RefList(None)

if not extra:
    o.fatal('must specify a target')
if len(extra) > 1:
    o.fatal('only one target file allowed')
if opt.bupm and opt.meta:
    o.fatal('--meta and --bupm are incompatible')
    
target = extra[0]

if not re.match(r'/*[^/]+/[^/]+', target):
    o.fatal("path %r doesn't include a branch and revision" % target)

try:
    n = top.lresolve(target)
except vfs.NodeError, e:
    o.fatal(e)

if isinstance(n, vfs.FakeSymlink):
    # Source is actually /foo/what, i.e. a top-level commit
    # like /foo/latest, which is a symlink to ../.commit/SHA.
    # So dereference it.
    target = n.dereference()

if opt.bupm:
    if not stat.S_ISDIR(n.mode):
        o.fatal('%r is not a directory' % target)
    mfile = n.metadata_file() # VFS file -- cannot close().
    if mfile:
        meta_stream = mfile.open()
        sys.stdout.write(meta_stream.read())
elif opt.meta:
    sys.stdout.write(n.metadata().encode())
else:
    if stat.S_ISREG(n.mode):
        for b in chunkyreader(n.open()):
            sys.stdout.write(b)
    else:
        o.fatal('%r is not a plain file' % target)

if saved_errors:
    log('warning: %d errors encountered\n' % len(saved_errors))
    sys.exit(1)
