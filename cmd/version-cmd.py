#!/usr/bin/env python
import sys, os, glob
from bup import options, _version

optspec = """
bup version [--date|--commit|--tag]
--
date    display the date this version of bup was created
commit  display the git commit id of this version of bup
tag     display the tag name of this version.  If no tag is available, display the commit id
"""
o = options.Options('bup version', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

def autoname(names):
    names = names.strip()
    assert(names[0] == '(')
    assert(names[-1] == ')')
    names = names[1:-1]
    l = [n.strip() for n in names.split(',')]
    for n in l:
        if n.startswith('tag: bup-'):
            return n[9:]


total = (opt.date or 0) + (opt.commit or 0) + (opt.tag or 0)
if total > 1:
    o.fatal('at most one option expected')

if opt.date:
    print _version.DATE.split(' ')[0]
elif opt.commit:
    print _version.COMMIT
else:
    print autoname(_version.NAMES) or 'unknown-%s' % _version.COMMIT[:7]
