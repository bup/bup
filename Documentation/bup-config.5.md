% bup-config(5) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-config - bup configuration options

# DESCRIPTION

The following options may be set in the relevant `git` config
(`git-config(1)`).

# OPTIONS

bup.split.files
:   This setting determines the number of fixed bits in the hash-split
    algorithm that lead to a chunk boundary, and thus the average size
    of objects. This represents a trade-off between the efficiency of
    the deduplication (fewer bits means better deduplication) and the
    amount of metadata to keep on disk and RAM usage during repo
    operations (more bits means fewer objects, means less metadata
    space and RAM use).  The expected average block size is 2^bits (1
    << bits), a sufficiently small change in a file would cause that
    much new data to be saved (plus tree metadata). The maximum blob
    size is 4x that. The default of this setting is 13 for backward
    compatibility, but it is recommended to change this to a higher
    value (e.g. 16) on all but very small repos.

    *NOTE:* Changing this value in an existing repository will
    duplicate data because it causes the split boundaries to change,
    so subsequent saves will not deduplicate against the existing
    data; they will just store the data again.

    *NOTE:* As with `bup.split.trees` below (see NOTE), using the same
    index for repositories with different `bup.split.files` settings
    will result in the index optimizations not working correctly, and
    so `bup save` will have to completely re-read files that haven't
    been modified, which is expensive.

bup.split.trees
:   When this boolean option is set to true, `bup` will attempt to
    split trees (directories) when writing to the repository during,
    for example `bup save ...`, `bup gc ..`, etc.  This can notably
    decrease the size of the new data added to the repository when
    large directories have changed (e.g. large active Maildirs).  See
    "Handling large directories" in the DESIGN in the `bup` source for
    additional information.

    *NOTE:* Using the same index to save to repositories that have
    differing values for this option can decrease performance because
    the index includes hashes for directories that have been saved and
    changing this option changes the hashes for directories that are
    affected by splitting.

    A directory tree's hash allows bup to avoid traversing the
    directory if the index indicates that it didn't otherwise change
    and the tree object with that hash already exists in the
    destination repository.  Since the the value of this setting
    changes the hashes of splittable trees, the hash in the index
    won't be found in a repository that has a different
    `bup.split.trees` value from the one to which that tree was last
    saved.  As a result, any (usually big) directory subject to tree
    splitting will have to be re-read and its related hashes
    recalculated.

pack.packSizeLimit
:   Respected when writing pack files (e.g. via `bup save ...`).
    Currently read from the repository to which the pack files are
    being written, excepting `bup on REMOTE...` which incorrectly
    reads the value from the `REMOTE` repository.

# SEE ALSO

`git-config`(1)

# BUP

Part of the `bup`(1) suite.
