% bup-rm(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-rm - remove references to archive content

# SYNOPSIS

bup rm [-#|\--verbose] <*branch*|*save*...>

# DESCRIPTION

`bup rm` removes the indicated *branch*es (backup sets) and *save*s.
By itself, this command does not delete any actual data (nor recover
any storage space), but it may make it very difficult or impossible to
refer to the deleted items, unless there are other references to them
(e.g. tags).

A subsequent garbage collection by `bup gc` may permanently delete
data that is no longer reachable from the remaining branches or tags
and reclaim the related storage space.  (The same would apply to a
`git gc` on the repository, but the safety of running `git gc` on a
bup repository has not been carefully evaluated, and should be
avoided.)

If you are familiar with `git`(1), removing branches is similar to
`git branch -D BRANCH` and removing saves is like a `git-rebase
--interactive` that removes commits.

WARNING: This is one of the few bup commands that modifies your
archive in intentionally destructive ways.

# OPTIONS

-v, \--verbose
:   increase verbosity (can be used more than once).

-*#*, \--compress=*#*
:   set the compression level to # (a value from 0-9, where
    9 is the highest and 0 is no compression).  The default
    is 6.  This applies to the rewritten branches (commits).

# EXAMPLES

    # Delete the backup set (branch) foo and a save in bar.
    $ bup rm /foo /bar/2014-10-21-214720

# SEE ALSO

`bup-gc`(1), `bup-save`(1), `bup-fsck`(1), and `bup-tag`(1)

# BUP

Part of the `bup`(1) suite.
