#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

# Copyright (C) 2010 Rob Browning
#
# This code is covered under the terms of the GNU Library General
# Public License as described in the bup LICENSE file.

from __future__ import absolute_import, print_function
import sys, stat, errno

from bup import metadata, options, xstat
from bup.compat import argv_bytes
from bup.helpers import add_error, handle_ctrl_c, parse_timestamp, saved_errors, \
    add_error, log
from bup.io import byte_stream


def parse_timestamp_arg(field, value):
    res = str(value) # Undo autoconversion.
    try:
        res = parse_timestamp(res)
    except ValueError as ex:
        if ex.args:
            o.fatal('unable to parse %s resolution "%s" (%s)'
                    % (field, value, ex))
        else:
            o.fatal('unable to parse %s resolution "%s"' % (field, value))

    if res != 1 and res % 10:
        o.fatal('%s resolution "%s" must be a power of 10' % (field, value))
    return res


optspec = """
bup xstat pathinfo [OPTION ...] <PATH ...>
--
v,verbose       increase log output (can be used more than once)
q,quiet         don't show progress meter
exclude-fields= exclude comma-separated fields
include-fields= include comma-separated fields (definitive if first)
atime-resolution=  limit s, ms, us, ns, 10ns (value must be a power of 10) [ns]
mtime-resolution=  limit s, ms, us, ns, 10ns (value must be a power of 10) [ns]
ctime-resolution=  limit s, ms, us, ns, 10ns (value must be a power of 10) [ns]
"""

target_filename = b''
active_fields = metadata.all_fields

handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, remainder) = o.parse(sys.argv[1:])

atime_resolution = parse_timestamp_arg('atime', opt.atime_resolution)
mtime_resolution = parse_timestamp_arg('mtime', opt.mtime_resolution)
ctime_resolution = parse_timestamp_arg('ctime', opt.ctime_resolution)

treat_include_fields_as_definitive = True
for flag, value in flags:
    if flag == '--exclude-fields':
        exclude_fields = frozenset(value.split(','))
        for f in exclude_fields:
            if not f in metadata.all_fields:
                o.fatal(f + ' is not a valid field name')
        active_fields = active_fields - exclude_fields
        treat_include_fields_as_definitive = False
    elif flag == '--include-fields':
        include_fields = frozenset(value.split(','))
        for f in include_fields:
            if not f in metadata.all_fields:
                o.fatal(f + ' is not a valid field name')
        if treat_include_fields_as_definitive:
            active_fields = include_fields
            treat_include_fields_as_definitive = False
        else:
            active_fields = active_fields | include_fields

opt.verbose = opt.verbose or 0
opt.quiet = opt.quiet or 0
metadata.verbose = opt.verbose - opt.quiet

sys.stdout.flush()
out = byte_stream(sys.stdout)

first_path = True
for path in remainder:
    path = argv_bytes(path)
    try:
        m = metadata.from_path(path, archive_path = path)
    except (OSError,IOError) as e:
        if e.errno == errno.ENOENT:
            add_error(e)
            continue
        else:
            raise
    if metadata.verbose >= 0:
        if not first_path:
            out.write(b'\n')
        if atime_resolution != 1:
            m.atime = (m.atime / atime_resolution) * atime_resolution
        if mtime_resolution != 1:
            m.mtime = (m.mtime / mtime_resolution) * mtime_resolution
        if ctime_resolution != 1:
            m.ctime = (m.ctime / ctime_resolution) * ctime_resolution
        out.write(metadata.detailed_bytes(m, active_fields))
        out.write(b'\n')
        first_path = False

if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    sys.exit(1)
else:
    sys.exit(0)
