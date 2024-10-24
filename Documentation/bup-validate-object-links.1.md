% bup-validate-object-links(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-validate-object-links - scan the respository for broken object links

# SYNOPSIS

bup validate-object-links

# DESCRIPTION

`bup validate-object-links` scans the objects in the repository for
and reports any "broken links" it finds, i.e. any links from a tree or
commit in the repository to an object that doesn't exist.  Currently,
it doesn't include "loose objects" (those not in packfiles -- which
git may create, but bup doesn't), and it can't handle tag objects
(which bup also doesn't create).

Whenever a broken link (missing reference) is found, an ASCII encoded
line formatted like this will be printed to standard output:

    no MISSING_HASH for PARENT_HASH

# EXIT STATUS

The exit status will be 1 if any broken links are found, 0 if none are
found, and some other positive integer for other failures.

# SEE ALSO

`bup-fsck`(1)

# BUP

Part of the `bup`(1) suite.
