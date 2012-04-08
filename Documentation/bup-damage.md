% bup-damage(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-damage - randomly destroy blocks of a file

# SYNOPSIS

bup damage [-n count] [-s maxsize] [\--percent pct] [-S seed]
[\--equal] \<filenames...\>

# DESCRIPTION

Use `bup damage` to deliberately destroy blocks in a
`.pack` or `.idx` file (from `.bup/objects/pack`) to test
the recovery features of `bup-fsck`(1) or other programs.

*THIS PROGRAM IS EXTREMELY DANGEROUS AND WILL DESTROY YOUR
DATA*

`bup damage` is primarily useful for automated or manual tests
of data recovery tools, to reassure yourself that the tools
actually work.

# OPTIONS

-n, \--num=*numblocks*
:   the number of separate blocks to damage in each file
    (default 10).
    Note that it's possible for more than one damaged
    segment to fall in the same `bup-fsck`(1) recovery block,
    so you might not damage as many recovery blocks as you
    expect.  If this is a problem, use `--equal`.

-s, \--size=*maxblocksize*
:   the maximum size, in bytes, of each damaged block
    (default 1 unless `--percent` is specified).  Note that
    because of the way `bup-fsck`(1) works, a multi-byte
    block could fall on the boundary between two recovery
    blocks, and thus damaging two separate recovery blocks. 
    In small files, it's also possible for a damaged block
    to be larger than a recovery block.  If these issues
    might be a problem, you should use the default damage
    size of one byte.
    
\--percent=*maxblockpercent*
:   the maximum size, in percent of the original file, of
    each damaged block.  If both `--size` and `--percent`
    are given, the maximum block size is the minimum of the
    two restrictions.  You can use this to ensure that a
    given block will never damage more than one or two
    `git-fsck`(1) recovery blocks.
    
-S, \--seed=*randomseed*
:   seed the random number generator with the given value. 
    If you use this option, your tests will be repeatable,
    since the damaged block offsets, sizes, and contents
    will be the same every time.  By default, the random
    numbers are different every time (so you can run tests
    in a loop and repeatedly test with different
    damage each time).
    
\--equal
:   instead of choosing random offsets for each damaged
    block, space the blocks equally throughout the file,
    starting at offset 0.  If you also choose a correct
    maximum block size, this can guarantee that any given
    damage block never damages more than one `git-fsck`(1)
    recovery block.  (This is also guaranteed if you use
    `-s 1`.)
    
# EXAMPLE

    # make a backup in case things go horribly wrong
    cp -a ~/.bup/objects/pack ~/bup-packs.bak
    
    # generate recovery blocks for all packs
    bup fsck -g
    
    # deliberately damage the packs
    bup damage -n 10 -s 1 -S 0 ~/.bup/objects/pack/*.{pack,idx}
    
    # recover from the damage
    bup fsck -r

# SEE ALSO

`bup-fsck`(1), `par2`(1)

# BUP

Part of the `bup`(1) suite.
