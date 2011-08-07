#!/usr/bin/env python
# Copyright (C) 2010 Rob Browning
#
# This code is covered under the terms of the GNU Library General
# Public License as described in the bup LICENSE file.
import sys, stat, errno
from bup import metadata, options, xstat
from bup.helpers import handle_ctrl_c, saved_errors, add_error, log

optspec = """
bup xstat pathinfo [OPTION ...] <PATH ...>
--
v,verbose       increase log output (can be used more than once)
q,quiet         don't show progress meter
exclude-fields= exclude comma-separated fields
include-fields= include comma-separated fields (definitive if first)
"""

target_filename = ''
active_fields = metadata.all_fields

handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, remainder) = o.parse(sys.argv[1:])

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

first_path = True
for path in remainder:
    try:
        m = metadata.from_path(path, archive_path = path)
    except (OSError,IOError), e:
        if e.errno == errno.ENOENT:
            add_error(e)
            continue
        else:
            raise
    if metadata.verbose >= 0:
        if not first_path:
            print
        print metadata.detailed_str(m, active_fields)
        first_path = False

if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    sys.exit(1)
else:
    sys.exit(0)
