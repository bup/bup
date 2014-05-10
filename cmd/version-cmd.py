#!/usr/bin/env python
import sys
from bup import options
from bup import _version

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


def version_date():
    """Format bup's version date string for output."""
    return _version.DATE.split(' ')[0]


def version_commit():
    """Get the commit hash of bup's current version."""
    return _version.COMMIT


def version_tag():
    """Format bup's version tag (the official version number).

    When generated from a commit other than one pointed to with a tag, the
    returned string will be "unknown-" followed by the first seven positions of
    the commit hash.
    """
    names = _version.NAMES.strip()
    assert(names[0] == '(')
    assert(names[-1] == ')')
    names = names[1:-1]
    l = [n.strip() for n in names.split(',')]
    for n in l:
        if n.startswith('tag: bup-'):
            return n[9:]
    return 'unknown-%s' % _version.COMMIT[:7]


if opt.date:
    print version_date()
elif opt.commit:
    print version_commit()
else:
    print version_tag()
