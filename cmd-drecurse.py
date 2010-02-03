#!/usr/bin/env python
import options, drecurse
from helpers import *

optspec = """
bup drecurse <path>
--
x,xdev   don't cross filesystem boundaries
q,quiet  don't actually print filenames
"""
o = options.Options('bup drecurse', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) != 1:
    log("drecurse: exactly one filename expected\n")
    o.usage()

for (name,st) in drecurse.recursive_dirlist(extra, opt.xdev):
    if not opt.quiet:
        print name
