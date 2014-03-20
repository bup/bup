% bup-midx(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-midx - create a multi-index (`.midx`) file from several `.idx` files

# SYNOPSIS

bup midx [-o *outfile*] \<-a|-f|*idxnames*...\>

# DESCRIPTION

`bup midx` creates a multi-index (`.midx`) file from one or more
git pack index (`.idx`) files.

Note: you should no longer need to run this command by hand.
It gets run automatically by `bup-save`(1) and similar
commands.

# OPTIONS

-o, \--output=*filename.midx*
:   use the given output filename for the `.midx` file.
    Default is auto-generated.

-a, \--auto
:   automatically generate new `.midx` files for any `.idx`
    files where it would be appropriate.

-f, \--force
:   force generation of a single new `.midx` file containing
    *all* your `.idx` files, even if other `.midx` files
    already exist.  This will result in the fastest backup
    performance, but may take a long time to run.

\--dir=*packdir*
:   specify the directory containing the `.idx`/`.midx` files
    to work with.  The default is $BUP_DIR/objects/pack and
    $BUP_DIR/indexcache/*.

\--max-files
:   maximum number of `.idx` files to open at a time.  You
    can use this if you have an especially small number of file
    descriptors available, so that midx can complete
    (though possibly non-optimally) even if it can't open
    all your `.idx` files at once.  The default value of this
    option should be fine for most people.
    
\--check
:   validate a `.midx` file by ensuring that all objects in
    its contained `.idx` files exist inside the `.midx`.  May
    be useful for debugging.


# EXAMPLES
    $ bup midx -a
    Merging 21 indexes (2278559 objects).
    Table size: 524288 (17 bits)
    Reading indexes: 100.00% (2278559/2278559), done.
    midx-b66d7c9afc4396187218f2936a87b865cf342672.midx
    
# DISCUSSION

By default, bup uses git-formatted pack files, which
consist of a pack file (containing objects) and an idx
file (containing a sorted list of object names and their
offsets in the .pack file).

Normal idx files are convenient because it means you can use
`git`(1) to access your backup datasets.  However, idx
files can get slow when you have a lot of very large packs
(which git typically doesn't have, but bup often does).

bup `.midx` files consist of a single sorted list of all the objects
contained in all the .pack files it references.  This list
can be binary searched in about log2(m) steps, where m is
the total number of objects.

To further speed up the search, midx files also have a
variable-sized fanout table that reduces the first n
steps of the binary search.  With the help of this fanout
table, bup can narrow down which page of the midx file a
given object id would be in (if it exists) with a single
lookup.  Thus, typical searches will only need to swap in
two pages: one for the fanout table, and one for the object
id.

midx files are most useful when creating new backups, since
searching for a nonexistent object in the repository
necessarily requires searching through *all* the index
files to ensure that it does not exist.  (Searching for
objects that *do* exist can be optimized; for example,
consecutive objects are often stored in the same pack, so
we can search that one first using an MRU algorithm.)


# SEE ALSO

`bup-save`(1), `bup-margin`(1), `bup-memtest`(1)

# BUP

Part of the `bup`(1) suite.
