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
bup_python="$(dirname "$0")/../../config/bin/python" || exit $?
exec "$bup_python" "$0"
"""
# end of bup preamble

# Copyright (C) 2010 Rob Browning
#
# This code is covered under the terms of the GNU Library General
# Public License as described in the bup LICENSE file.

# TODO: Add tar-like -C option.

from __future__ import absolute_import
import os, sys

sys.path[:0] = [os.path.dirname(os.path.realpath(__file__)) + '/..']

from bup import compat, metadata
from bup import options
from bup.compat import argv_bytes
from bup.io import byte_stream
from bup.helpers import handle_ctrl_c, log, saved_errors


def open_input(name):
    if not name or name == b'-':
        return byte_stream(sys.stdin)
    return open(name, 'rb')


def open_output(name):
    if not name or name == b'-':
        sys.stdout.flush()
        return byte_stream(sys.stdout)
    return open(name, 'wb')


optspec = """
bup meta --create [OPTION ...] <PATH ...>
bup meta --list [OPTION ...]
bup meta --extract [OPTION ...]
bup meta --start-extract [OPTION ...]
bup meta --finish-extract [OPTION ...]
bup meta --edit [OPTION ...] <PATH ...>
--
c,create       write metadata for PATHs to stdout (or --file)
t,list         display metadata
x,extract      perform --start-extract followed by --finish-extract
start-extract  build tree matching metadata provided on standard input (or --file)
finish-extract finish applying standard input (or --file) metadata to filesystem
edit           alter metadata; write to stdout (or --file)
f,file=        specify source or destination file
R,recurse      recurse into subdirectories
xdev,one-file-system  don't cross filesystem boundaries
numeric-ids    apply numeric IDs (user, group, etc.) rather than names
symlinks       handle symbolic links (default is true)
paths          include paths in metadata (default is true)
set-uid=       set metadata uid (via --edit)
set-gid=       set metadata gid (via --edit)
set-user=      set metadata user (via --edit)
unset-user     remove metadata user (via --edit)
set-group=     set metadata group (via --edit)
unset-group    remove metadata group (via --edit)
v,verbose      increase log output (can be used more than once)
q,quiet        don't show progress meter
"""

handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, remainder) = o.parse(['--paths', '--symlinks', '--recurse']
                                  + compat.argv[1:])

opt.verbose = opt.verbose or 0
opt.quiet = opt.quiet or 0
metadata.verbose = opt.verbose - opt.quiet
opt.file = argv_bytes(opt.file) if opt.file else None

action_count = sum([bool(x) for x in [opt.create, opt.list, opt.extract,
                                      opt.start_extract, opt.finish_extract,
                                      opt.edit]])
if action_count > 1:
    o.fatal("bup: only one action permitted: --create --list --extract --edit")
if action_count == 0:
    o.fatal("bup: no action specified")

if opt.create:
    if len(remainder) < 1:
        o.fatal("no paths specified for create")
    output_file = open_output(opt.file)
    metadata.save_tree(output_file,
                       [argv_bytes(r) for r in remainder],
                       recurse=opt.recurse,
                       write_paths=opt.paths,
                       save_symlinks=opt.symlinks,
                       xdev=opt.xdev)
elif opt.list:
    if len(remainder) > 0:
        o.fatal("cannot specify paths for --list")
    src = open_input(opt.file)
    metadata.display_archive(src, open_output(b'-'))
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
elif opt.edit:
    if len(remainder) < 1:
        o.fatal("no paths specified for edit")
    output_file = open_output(opt.file)

    unset_user = False # True if --unset-user was the last relevant option.
    unset_group = False # True if --unset-group was the last relevant option.
    for flag in flags:
        if flag[0] == '--set-user':
            unset_user = False
        elif flag[0] == '--unset-user':
            unset_user = True
        elif flag[0] == '--set-group':
            unset_group = False
        elif flag[0] == '--unset-group':
            unset_group = True

    for path in remainder:
        f = open(argv_bytes(path), 'rb')
        try:
            for m in metadata._ArchiveIterator(f):
                if opt.set_uid is not None:
                    try:
                        m.uid = int(opt.set_uid)
                    except ValueError:
                        o.fatal("uid must be an integer")

                if opt.set_gid is not None:
                    try:
                        m.gid = int(opt.set_gid)
                    except ValueError:
                        o.fatal("gid must be an integer")

                if unset_user:
                    m.user = b''
                elif opt.set_user is not None:
                    m.user = argv_bytes(opt.set_user)

                if unset_group:
                    m.group = b''
                elif opt.set_group is not None:
                    m.group = argv_bytes(opt.set_group)

                m.write(output_file)
        finally:
            f.close()


if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    sys.exit(1)
else:
    sys.exit(0)
