% bup-fsck(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-fsck - verify or repair a bup repository

# SYNOPSIS

bup fsck [-r] [-g] [-v] [\--quick] [-j *jobs*] [\--par2-ok]
[\--disable-par2] [filenames...]

# DESCRIPTION

`bup fsck` is a tool for validating bup repositories in the
same way that `git fsck` validates git repositories.

It can also generate and/or use "recovery blocks" using the
`par2`(1) tool (if you have it installed).  This allows you
to recover from damaged blocks covering up to 5% of your
`.pack` files.

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

*WARNING*: bup fsck's recovery features are not available
unless you have the free `par2`(1) package installed on
your bup server.

*WARNING*: bup fsck obviously cannot recover from a
complete disk failure.  If your backups are important, you
need to carefully consider redundancy (such as using RAID
for multi-disk redundancy, or making off-site backups for
site redundancy).

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


# EXAMPLE

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

# SEE ALSO

`bup-damage`(1), `fsck`(1), `git-fsck`(1)

# BUP

Part of the `bup`(1) suite.
