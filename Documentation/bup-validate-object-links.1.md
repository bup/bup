% bup-validate-object-links(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-validate-object-links - scan the repository for broken object links

# SYNOPSIS

bup validate-object-links

# DESCRIPTION

`bup validate-object-links` scans the objects in the repository and
reports any references from a tree or commit to an object that does
not exist in the repository.  Currently, it doesn't scan "loose
objects" (those not in packfiles) or notice them when checking for
existence, and it cannot handle tag objects.  Note that `bup` doesn't
create tags or loose objects, but `git` may.

The existence check only consults the repository indexes; it does not
try to read the object, so it could be misled by an incorrect index.

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
