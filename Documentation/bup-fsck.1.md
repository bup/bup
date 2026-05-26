% bup-fsck(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-fsck - verify or repair a bup repository

# SYNOPSIS

bup fsck [-r] [-g] [-v] [\--quick] [-j *jobs*] [\--par2-ok]
[\--disable-par2] [packfile...]

# DESCRIPTION

When *packfile*s (which must end in .pack) are specified, pack-related
operations are limited to those files, otherwise all packfiles in the
current repository are considered.

Currently `bup fsck` checks the data in the repository for corruption.
More specifically, it checks the integrity of the data *packfile*s and
their corresponding indexes to ensure that they have not changed since
they were written.  It does not check higher level concerns like
connectivity (missing objects), e.g. whether all the data referred to
by a save actually exists in the repository.  For some higher level
checks, see `bup-validate-object-links`(1) and `bup-validate-refs`(1).
The checks `bup fsck` performs are focused on detecting, and
potentially repairing, file corruption, while the higher level
problems are more likely to be caused by (hopefully rarer) bugs.

When checking the packfiles and indexes, right now fsck will normally
rely on `git-verify-pack`(1), but with `--quick` (more below), bup
will just check the index and packfile checksums itself.

To allow repairs, fsck must be asked via `--generate` to generate
`par2`(1) "recovery blocks" (if you have it installed).  These blocks
allow you to recover from damage affecting up to 5% of your `.pack`
files.

In a normal backup system, damaged blocks are less
important, because there tends to be enough data duplicated
between backup sets that a single damaged backup set is
non-critical.  In a deduplicating backup system like bup,
however, no block is ever stored more than once, even if it
is used in every single backup.  If that block were to be
unrecoverable, *all* your backup sets would be
damaged at once.  Thus, it's important to be able to verify
the integrity of your backups and recover from disk errors
if they occur.

When attempting to `--repair`, bup will exit with status 1 if and only
if repairs were needed and were successful, and there were no other
errors.

*WARNING*: bup fsck obviously cannot recover from a
complete disk failure.  If your backups are important, you
need to carefully consider redundancy (such as using RAID
for multi-disk redundancy, or making off-site backups for
site redundancy).

When asked to examine all packfiles (i.e. when no *packfile*s are
specified), fsck will report any files that appear to be related to a
pack file that no longer exists.  Previous versions of `bup gc` can
cause this to happen because they did not remove all of the related
files when removing a pack file.

# OPTIONS

-r, \--repair
:   attempt to repair any damaged packs using
    existing recovery blocks.  (Requires `par2`(1).)
    
-g, \--generate
:   generate recovery blocks for any packs that don't
    already have them.  (Requires `par2`(1).)

-v, \--verbose
:   increase verbosity (can be used more than once).

\--quick
:   don't run a full `git verify-pack` on each pack file;
    instead just check the final checksum.  This can cause
    a significant speedup with no obvious decrease in
    reliability.  However, you may want to avoid this
    option if you're paranoid.  Has no effect on packs that
    already have recovery information.
    
-j, \--jobs=*numjobs*
:   maximum number of pack verifications to run at a time. 
    The optimal value for this option depends how fast your
    CPU can verify packs vs. your disk throughput.  If you
    run too many jobs at once, your disk will get saturated
    by seeking back and forth between files and performance
    will actually decrease, even if *numjobs* is less than
    the number of CPU cores on your system.  You can
    experiment with this option to find the optimal value.
    
\--par2-ok
:   immediately return 0 if `par2`(1) is installed and
    working, or 1 otherwise.  Do not actually check
    anything.
    
\--disable-par2
:   pretend that `par2`(1) is not installed, and ignore all
    recovery blocks.


# EXAMPLES
    # generate recovery blocks for all packs that don't
    # have them
    bup fsck -g
    
    # generate recovery blocks for a particular pack
    bup fsck -g ~/.bup/objects/pack/153a1420cb1c8*.pack
    
    # check all packs for correctness (can be very slow!)
    bup fsck
    
    # check all packs for correctness and recover any
    # damaged ones
    bup fsck -r
    
    # check a particular pack for correctness and recover
    # it if damaged
    bup fsck -r ~/.bup/objects/pack/153a1420cb1c8*.pack
    
    # check if recovery blocks are available on this system
    if bup fsck --par2-ok; then
    	echo "par2 is ok"
    fi

# EXIT STATUS

Exits with 1 if `--repair` was requested, needed, successful, and
there were no other errors.  Otherwise exits with 0 if there were no
errors and a value other than zero or one for errors.

# SEE ALSO

`bup-damage`(1), `fsck`(1), `git-fsck`(1),
`bup-validate-object-links`(1), and `bup-validate-refs`(1)

# BUP

Part of the `bup`(1) suite.
