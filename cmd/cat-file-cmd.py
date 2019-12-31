#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import re, stat, sys

from bup import options, git, vfs
from bup.compat import argv_bytes
from bup.helpers import chunkyreader, handle_ctrl_c, log, saved_errors
from bup.io import byte_stream
from bup.repo import LocalRepo

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

if not extra:
    o.fatal('must specify a target')
if len(extra) > 1:
    o.fatal('only one target file allowed')
if opt.bupm and opt.meta:
    o.fatal('--meta and --bupm are incompatible')
    
target = argv_bytes(extra[0])

if not re.match(br'/*[^/]+/[^/]+', target):
    o.fatal("path %r doesn't include a branch and revision" % target)

repo = LocalRepo()
resolved = vfs.resolve(repo, target, follow=False)
leaf_name, leaf_item = resolved[-1]
if not leaf_item:
    log('error: cannot access %r in %r\n'
        % ('/'.join(name for name, item in resolved), path))
    sys.exit(1)

mode = vfs.item_mode(leaf_item)

sys.stdout.flush()
out = byte_stream(sys.stdout)

if opt.bupm:
    if not stat.S_ISDIR(mode):
        o.fatal('%r is not a directory' % target)
    _, bupm_oid = vfs.tree_data_and_bupm(repo, leaf_item.oid)
    if bupm_oid:
        with vfs.tree_data_reader(repo, bupm_oid) as meta_stream:
            out.write(meta_stream.read())
elif opt.meta:
    augmented = vfs.augment_item_meta(repo, leaf_item, include_size=True)
    out.write(augmented.meta.encode())
else:
    if stat.S_ISREG(mode):
        with vfs.fopen(repo, leaf_item) as f:
            for b in chunkyreader(f):
                out.write(b)
    else:
        o.fatal('%r is not a plain file' % target)

if saved_errors:
    log('warning: %d errors encountered\n' % len(saved_errors))
    sys.exit(1)
