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
numeric-ids    apply numeric IDs (user, group, etc.), not names, during restore
symlinks       handle symbolic links (default is true)
paths          include paths in metadata (default is true)
v,verbose      increase log output (can be used more than once)
q,quiet        don't show progress meter
"""

action = None
target_filename = ''
should_recurse = False
restore_numeric_ids = False
include_paths = True
handle_symlinks = True

handle_ctrl_c()

o = options.Options('bup meta', optspec)
(opt, flags, remainder) = o.parse(sys.argv[1:])

for flag, value in flags:
    if flag == '--create' or flag == '-c':
        action = 'create'
    elif flag == '--list' or flag == '-t':
        action = 'list'
    elif flag == '--extract' or flag == '-x':
        action = 'extract'
    elif flag == '--start-extract':
        action = 'start-extract'
    elif flag == '--finish-extract':
        action = 'finish-extract'
    elif flag == '--file' or flag == '-f':
        target_filename = value
    elif flag == '--recurse' or flag == '-R':
        should_recurse = True
    elif flag == '--no-recurse':
        should_recurse = False
    elif flag == '--numeric-ids':
        restore_numeric_ids = True
    elif flag == '--no-numeric-ids':
        restore_numeric_ids = False
    elif flag == '--paths':
        include_paths = True
    elif flag == '--no-paths':
        include_paths = False
    elif flag == '--symlinks':
        handle_symlinks = True
    elif flag == '--no-symlinks':
        handle_symlinks = False
    elif flag == '--verbose' or flag == '-v':
        metadata.verbose += 1
    elif flag == '--quiet' or flag == '-q':
        metadata.verbose = 0

if not action:
    o.fatal("no action specified")

if action == 'create':
    if len(remainder) < 1:
        o.fatal("no paths specified for create")
    if target_filename != '-':
        output_file = open(target_filename, 'w')
    else:
        output_file = sys.stdout
    metadata.save_tree(output_file,
                       remainder,
                       recurse=should_recurse,
                       write_paths=include_paths,
                       save_symlinks=handle_symlinks)

elif action == 'list':
    if len(remainder) > 0:
        o.fatal("cannot specify paths for --list")
    if target_filename != '-':
        src = open(target_filename, 'r')
    else:
        src = sys.stdin
    metadata.display_archive(src)

elif action == 'start-extract':
    if len(remainder) > 0:
        o.fatal("cannot specify paths for --start-extract")
    if target_filename != '-':
        src = open(target_filename, 'r')
    else:
        src = sys.stdin
    metadata.start_extract(src, create_symlinks=handle_symlinks)

elif action == 'finish-extract':
    if len(remainder) > 0:
        o.fatal("cannot specify paths for --finish-extract")
    if target_filename != '-':
        src = open(target_filename, 'r')
    else:
        src = sys.stdin
    num_ids = restore_numeric_ids
    metadata.finish_extract(src, restore_numeric_ids=num_ids)

elif action == 'extract':
    if len(remainder) > 0:
        o.fatal("cannot specify paths for --extract")
    if target_filename != '-':
        src = open(target_filename, 'r')
    else:
        src = sys.stdin
    metadata.extract(src,
                     restore_numeric_ids=restore_numeric_ids,
                     create_symlinks=handle_symlinks)

if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    sys.exit(1)
else:
    sys.exit(0)
