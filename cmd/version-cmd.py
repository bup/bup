#!/usr/bin/env python
import sys
from bup import options
from bup.helpers import *

optspec = """
bup version [--date|--commit|--tag]
--
date    display the date this version of bup was created
commit  display the git commit id of this version of bup
tag     display the tag name of this version.  If no tag is available, display the commit id
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])


total = (opt.date or 0) + (opt.commit or 0) + (opt.tag or 0)
if total > 1:
    o.fatal('at most one option expected')

if opt.date:
    print version_date()
elif opt.commit:
    print version_commit()
else:
    print version_tag()
