#!/usr/bin/env python

# Copyright (C) 2010 Rob Browning
#
# This code is covered under the terms of the GNU Library General
# Public License as described in the bup LICENSE file.

# TODO: Add tar-like -C option.
# TODO: Add tar-like -v support to --list.

import sys
from bup import metadata
from bup import options
from bup.helpers import handle_ctrl_c, log, saved_errors


def open_input(name):
    if name != '-':
        return open(name, 'r')
    else:
        return sys.stdin


optspec = """
bup meta --create [OPTION ...] <PATH ...>
bup meta --extract [OPTION ...]
bup meta --start-extract [OPTION ...]
bup meta --finish-extract [OPTION ...]
--
c,create       write metadata for PATHs to stdout (or --file)
t,list         display metadata
x,extract      perform --start-extract followed by --finish-extract
start-extract  build tree matching metadata provided on standard input (or --file)
finish-extract finish applying standard input (or --file) metadata to filesystem
f,file=        specify source or destination file
R,recurse      recurse into subdirectories
xdev,one-file-system  don't cross filesystem boundaries
numeric-ids    apply numeric IDs (user, group, etc.), not names, during restore
symlinks       handle symbolic links (default is true)
paths          include paths in metadata (default is true)
v,verbose      increase log output (can be used more than once)
q,quiet        don't show progress meter
"""

handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, remainder) = o.parse(['--paths', '--symlinks'] + sys.argv[1:])

opt.verbose = opt.verbose or 0
opt.quiet = opt.quiet or 0
metadata.verbose = opt.verbose - opt.quiet

action_count = sum([bool(x) for x in [opt.create, opt.list, opt.extract,
                                      opt.start_extract, opt.finish_extract]])
if action_count > 1:
    o.fatal("bup: only one action permitted: --create --list --extract")
if action_count == 0:
    o.fatal("bup: no action specified")

if opt.create:
    if len(remainder) < 1:
        o.fatal("no paths specified for create")
    if opt.file != '-':
        output_file = open(opt.file, 'w')
    else:
        output_file = sys.stdout
    metadata.save_tree(output_file,
                       remainder,
                       recurse=opt.recurse,
                       write_paths=opt.paths,
                       save_symlinks=opt.symlinks,
                       xdev=opt.xdev)
elif opt.list:
    if len(remainder) > 0:
        o.fatal("cannot specify paths for --list")
    src = open_input(opt.file)
    metadata.display_archive(src)
elif opt.start_extract:
    if len(remainder) > 0:
        o.fatal("cannot specify paths for --start-extract")
    src = open_input(opt.file)
    metadata.start_extract(src, create_symlinks=opt.symlinks)
elif opt.finish_extract:
    if len(remainder) > 0:
        o.fatal("cannot specify paths for --finish-extract")
    src = open_input(opt.file)
    metadata.finish_extract(src, restore_numeric_ids=opt.numeric_ids)
elif opt.extract:
    if len(remainder) > 0:
        o.fatal("cannot specify paths for --extract")
    src = open_input(opt.file)
    metadata.extract(src,
                     restore_numeric_ids=opt.numeric_ids,
                     create_symlinks=opt.symlinks)

if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    sys.exit(1)
else:
    sys.exit(0)
