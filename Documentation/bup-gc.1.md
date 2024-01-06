% bup-gc(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-gc - remove unreferenced, unneeded data

# SYNOPSIS

bup gc [-#|\--verbose] <*branch*|*save*...>

# DESCRIPTION

`bup gc` removes (permanently deletes) unreachable data from the
repository, data that isn't referred to directly or indirectly by the
current set of branches (backup sets) and tags.  But bear in mind that
given deduplication, deleting a save and running the garbage collector
might or might not actually delete anything (or reclaim any space).

With the current, proababilistic implementation, some fraction of the
unreachable data may be retained.  In exchange, the garbage collection
should require much less RAM than might by some more precise
approaches.

Typically, the garbage collector would be invoked after some set of
invocations of `bup rm`.

WARNING: This is one of the few bup commands that modifies your
archive in intentionally destructive ways.  Though if an attempt to
`join` or `restore` the data you still care about after a `gc`
succeeds, that's a fairly encouraging sign that the commands worked
correctly.  (The `dev/compare-trees` command in the source tree can be
used to help test before/after results.)

# OPTIONS

\--threshold=N
:   only rewrite a packfile if it's over N percent garbage; otherwise
    leave it alone.  The default threshold is 10%.

-v, \--verbose
: increase verbosity (can be used more than once).  With one -v, bup
    prints every directory name as it gets backed up.  With two -v,
    it also prints every filename.

-*#*, \--compress=*#*
:   set the compression level to # (a value from 0-9, where
    9 is the highest and 0 is no compression).  The default
    is 1 (fast, loose compression).

# EXAMPLES

    # Remove all saves of "home" and most of the otherwise unreferenced data.
    $ bup rm home
    $ bup gc

# SEE ALSO

`bup-rm`(1) and `bup-fsck`(1)

# BUP

Part of the `bup`(1) suite.
