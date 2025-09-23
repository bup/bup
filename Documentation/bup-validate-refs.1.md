% bup-validate-refs(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-validate-refs - check integrity of repository refs

# SYNOPSIS

bup validate-refs [--links] [*ref*...]

# DESCRIPTION

`bup validate-refs` can check repository references (e.g. saves) for
commits or trees (directories) that refer to missing objects,
reporting the path to any it finds. If no *ref*s are provided, it
checks all refs, otherwise it only checks those specified. If
`--links` is not specified, then it is implied.

At the moment, the broken path information is only logged to standard
error, and is not well specified (i.e. suitable for inspection, but
not parsing).

Also note that the current implementation may not report all paths to
a given missing object because it only examines each unique tree or
commit object once, no matter how often it appears within the refs
being examined.  This means that in order to find every save with
missing objects you would need to run the command separately for each
ref, which will almost certainly to be much more expensive than a
combined run because it can't skip subtrees that it has encountered
before.

# OPTIONS

\--links
:   check for commits or trees that refer to missing objects. This
    command can also be used to validate a save more quickly than
    attempting a `restore` or `join`ing the save to /dev/null, and
    much more quickly for multiple related saves, though it only
    checks for the existence of the leaf (blob) data, it does not
    attempt to read that data.

# EXIT STATUS

The exit status will be 1 if any broken links are found, 0 if none are
found, and some other positive integer for other failures.

# SEE ALSO

`bup-fsck`(1), `bup-join`(1), `bup-restore`(1)

# BUP

Part of the `bup`(1) suite.
