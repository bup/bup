% bup-margin(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-margin - figure out your deduplication safety margin

# SYNOPSIS

bup margin [options...]

# DESCRIPTION

`bup margin` iterates through all objects in your bup
repository, calculating the largest number of prefix bits
shared between any two entries.  This number, `n`,
identifies the longest subset of SHA-1 you could use and still
encounter a collision between your object ids.

For example, one system that was tested had a collection of
11 million objects (70 GB), and `bup margin` returned 45.
That means a 46-bit hash would be sufficient to avoid all
collisions among that set of objects; each object in that
repository could be uniquely identified by its first 46
bits.

The number of bits needed seems to increase by about 1 or 2
for every doubling of the number of objects.  Since SHA-1
hashes have 160 bits, that leaves 115 bits of margin.  Of
course, because SHA-1 hashes are essentially random, it's
theoretically possible to use many more bits with far fewer
objects.

If you're paranoid about the possibility of SHA-1
collisions, you can monitor your repository by running `bup
margin` occasionally to see if you're getting dangerously
close to 160 bits.

# OPTIONS

\--predict
:   Guess the offset into each index file where a
    particular object will appear, and report the maximum
    deviation of the correct answer from the guess.  This
    is potentially useful for tuning an interpolation
    search algorithm.
    
\--ignore-midx
:   don't use `.midx` files, use only `.idx` files.  This is
    only really useful when used with `--predict`.

    
# EXAMPLES
    $ bup margin
    Reading indexes: 100.00% (1612581/1612581), done.
    40
    40 matching prefix bits
    1.94 bits per doubling
    120 bits (61.86 doublings) remaining
    4.19338e+18 times larger is possible
    
    Everyone on earth could have 625878182 data sets
    like yours, all in one repository, and we would
    expect 1 object collision.
    
    $ bup margin --predict
    PackIdxList: using 1 index.
    Reading indexes: 100.00% (1612581/1612581), done.
    915 of 1612581 (0.057%) 
    

# SEE ALSO

`bup-midx`(1), `bup-save`(1)

# BUP

Part of the `bup`(1) suite.
