#!/usr/bin/env python
# Copyright (C) 2010 Rob Browning
#
# This code is covered under the terms of the GNU Library General
# Public License as described in the bup LICENSE file.
import sys, stat, errno
from bup import metadata, options, xstat
from bup.helpers import handle_ctrl_c, saved_errors, add_error, log


def fstimestr(fstime):
    (s, ns) = xstat.fstime_to_timespec(fstime)
    if(s < 0):
        s += 1
    if ns == 0:
        return '%d' % s
    else:
        return '%d.%09d' % (s, ns)


optspec = """
bup xstat pathinfo [OPTION ...] <PATH ...>
--
v,verbose       increase log output (can be used more than once)
q,quiet         don't show progress meter
exclude-fields= exclude comma-separated fields
include-fields= include comma-separated fields (definitive if first)
"""

target_filename = ''
all_fields = frozenset(['path',
                        'mode',
                        'link-target',
                        'rdev',
                        'uid',
                        'gid',
                        'owner',
                        'group',
                        'atime',
                        'mtime',
                        'ctime',
                        'linux-attr',
                        'linux-xattr',
                        'posix1e-acl'])
active_fields = all_fields

handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, remainder) = o.parse(sys.argv[1:])

treat_include_fields_as_definitive = True
for flag, value in flags:
    if flag == '--exclude-fields':
        exclude_fields = frozenset(value.split(','))
        for f in exclude_fields:
            if not f in all_fields:
                o.fatal(f + ' is not a valid field name')
        active_fields = active_fields - exclude_fields
        treat_include_fields_as_definitive = False
    elif flag == '--include-fields':
        include_fields = frozenset(value.split(','))
        for f in include_fields:
            if not f in all_fields:
                o.fatal(f + ' is not a valid field name')
        if treat_include_fields_as_definitive:
            active_fields = include_fields
            treat_include_fields_as_definitive = False
        else:
            active_fields = active_fields | include_fields

opt.verbose = opt.verbose or 0
opt.quiet = opt.quiet or 0
metadata.verbose = opt.verbose - opt.quiet

for path in remainder:
    try:
        m = metadata.from_path(path, archive_path = path)
    except (OSError,IOError), e:
        if e.errno == errno.ENOENT:
            add_error(e)
            continue
        else:
            raise
    if 'path' in active_fields:
        print 'path:', m.path
    if 'mode' in active_fields:
        print 'mode:', oct(m.mode)
    if 'link-target' in active_fields and stat.S_ISLNK(m.mode):
        print 'link-target:', m.symlink_target
    if 'rdev' in active_fields:
        print 'rdev:', m.rdev
    if 'uid' in active_fields:
        print 'uid:', m.uid
    if 'gid' in active_fields:
        print 'gid:', m.gid
    if 'owner' in active_fields:
        print 'owner:', m.owner
    if 'group' in active_fields:
        print 'group:', m.group
    if 'atime' in active_fields:
        # If we don't have utimensat, that means we have to use
        # utime(), and utime() has no way to set the mtime/atime of a
        # symlink.  Thus, the mtime/atime of a symlink is meaningless,
        # so let's not report it.  (That way scripts comparing
        # before/after won't trigger.)
        if xstat.lutime or not stat.S_ISLNK(m.mode):
            print 'atime: ' + fstimestr(m.atime)
        else:
            print 'atime: 0'
    if 'mtime' in active_fields:
        if xstat.lutime or not stat.S_ISLNK(m.mode):
            print 'mtime: ' + fstimestr(m.mtime)
        else:
            print 'mtime: 0'
    if 'ctime' in active_fields:
        print 'ctime: ' + fstimestr(m.ctime)
    if 'linux-attr' in active_fields and m.linux_attr:
        print 'linux-attr:', hex(m.linux_attr)
    if 'linux-xattr' in active_fields and m.linux_xattr:
        for name, value in m.linux_xattr:
            print 'linux-xattr: %s -> %s' % (name, repr(value))
    if 'posix1e-acl' in active_fields and m.posix1e_acl and metadata.posix1e:
        flags = metadata.posix1e.TEXT_ABBREVIATE
        if stat.S_ISDIR(m.mode):
            acl = m.posix1e_acl[0]
            default_acl = m.posix1e_acl[2]
            print acl.to_any_text('posix1e-acl: ', '\n', flags)
            print acl.to_any_text('posix1e-acl-default: ', '\n', flags)
        else:
            acl = m.posix1e_acl[0]
            print acl.to_any_text('posix1e-acl: ', '\n', flags)

if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    sys.exit(1)
else:
    sys.exit(0)
