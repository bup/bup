#!/usr/bin/env python
import sys, os
from bup import git, options
from bup.helpers import *

optspec = """
bup list-idx [--find=<prefix>] <idxfilenames...>
--
find=   display only objects that start with <prefix>
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

handle_ctrl_c()
opt.find = opt.find or ''

if not extra:
    o.fatal('you must provide at least one filename')

if len(opt.find) > 40:
    o.fatal('--find parameter must be <= 40 chars long')
else:
    if len(opt.find) % 2:
        s = opt.find + '0'
    else:
        s = opt.find
    try:
        bin = s.decode('hex')
    except TypeError:
        o.fatal('--find parameter is not a valid hex string')

find = opt.find.lower()

count = 0
for name in extra:
    try:
        ix = git.open_idx(name)
    except git.GitError, e:
        add_error('%s: %s' % (name, e))
        continue
    if len(opt.find) == 40:
        if ix.exists(bin):
            print name, find
    else:
        # slow, exhaustive search
        for _i in ix:
            i = str(_i).encode('hex')
            if i.startswith(find):
                print name, i
            qprogress('Searching: %d\r' % count)
            count += 1

if saved_errors:
    log('WARNING: %d errors encountered while saving.\n' % len(saved_errors))
    sys.exit(1)
