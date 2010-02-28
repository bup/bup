#!/usr/bin/env python
import options, drecurse
from helpers import *

optspec = """
bup drecurse <path>
--
x,xdev,one-file-system   don't cross filesystem boundaries
q,quiet  don't actually print filenames
profile  run under the python profiler
"""
o = options.Options('bup drecurse', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) != 1:
    o.fatal("exactly one filename expected")

it = drecurse.recursive_dirlist(extra, opt.xdev)
if opt.profile:
    import cProfile
    def do_it():
        for i in it:
            pass
    cProfile.run('do_it()')
else:
    if opt.quiet:
        for i in it:
            pass
    else:
        for (name,st) in it:
            print name

if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    sys.exit(1)
