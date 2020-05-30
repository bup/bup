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

from __future__ import absolute_import, print_function
import os.path, re, sys

sys.path[:0] = [os.path.dirname(os.path.realpath(__file__)) + '/..']

from bup import compat, options, version

version_rx = re.compile(r'^[0-9]+\.[0-9]+(\.[0-9]+)?(-[0-9]+-g[0-9abcdef]+)?$')

optspec = """
bup version [--date|--commit|--tag]
--
date    display the date this version of bup was created
commit  display the git commit id of this version of bup
tag     display the tag name of this version.  If no tag is available, display the commit id
"""
o = options.Options(optspec)
opt, flags, extra = o.parse(compat.argv[1:])


total = (opt.date or 0) + (opt.commit or 0) + (opt.tag or 0)
if total > 1:
    o.fatal('at most one option expected')


def version_date():
    """Format bup's version date string for output."""
    return version.DATE.split(' ')[0]


def version_commit():
    """Get the commit hash of bup's current version."""
    return version.COMMIT


def version_tag():
    """Format bup's version tag (the official version number).

    When generated from a commit other than one pointed to with a tag, the
    returned string will be "unknown-" followed by the first seven positions of
    the commit hash.
    """
    names = version.NAMES.strip()
    assert(names[0] == '(')
    assert(names[-1] == ')')
    names = names[1:-1]
    l = [n.strip() for n in names.split(',')]
    for n in l:
        if n.startswith('tag: ') and version_rx.match(n[5:]):
            return n[5:]
    return 'unknown-%s' % version.COMMIT[:7]


if opt.date:
    print(version_date())
elif opt.commit:
    print(version_commit())
else:
    print(version_tag())
