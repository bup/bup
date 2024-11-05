% bup-validate-ref-links(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-validate-ref-links - check repository refs for links to missing objects

# SYNOPSIS

bup validate-ref-links

# DESCRIPTION

`bup validate-ref-links` checks all the repository refs (e.g. saves)
for commits or subtrees that refer to missing objects and reports the
paths to any found.

At the moment, the broken path information is only logged to standard
error, and is not well specified (i.e. suitable for inspection, but
not parsing).

Also note that the current implementation may not report all paths to
a given missing object because it only examines each unique tree or
commit object once, no matter how often it appears within the refs
being examined.  This means that in order to find every broken save,
you would need to run the command separately for each ref, which is
likely to be much more expensive than a combined run because it can't
skip subtrees that it has encountered before.

# EXIT STATUS

The exit status will be 1 if any broken links are found, 0 if none are
found, and some other positive integer for other failures.

# SEE ALSO

`bup-fsck`(1)

# BUP

Part of the `bup`(1) suite.
