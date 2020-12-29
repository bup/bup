% bup-config(5) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-config - bup configuration options

# DESCRIPTION

The following options may be set in the relevant `git` config
(`git-config(1)`).

# OPTIONS

bup.server.deduplicate-writes (default `true`)
:   When `true` `bup-server`(1) checks each incoming object against its
    local index, and if the object already exists, the server suggests
    to the client that it download the `*.idx` file that the object
    was found in so that it can avoid sending duplicate data.

    When false the server does not check its local index before
    writing objects.  To avoid writing duplicate objects, the server
    tells the client to download all of its `*.idx` files at the start
    of the session.  This mode is useful on more limited server
    hardware (i.e. routers, slow NAS devices, etc.).

    If no value is set, and a `$BUP_DIR/dumb-server-mode` file exists,
    then `bup` will act as if this setting were `false`.

bup.split.files (default `legacy:13`)
:   Method used to split data for deduplication, for example by `bup
    save` or `bup split`. This determines the "granularity" of the
    deduplication, with larger values producing, on average, larger
    chunks. The value must be a string like `legacy:N` where the
    integer `N` must be greater than 12 and less than 22. The default
    of 13 provides backward compatibility, but it is recommended to
    increase this, say to 16, for all but very small repos.

    `N` specifies the number of fixed bits in the hash-split algorithm
    that when all set to one produce a chunk boundary, and thus it
    determines the average size of the deduplicated objects. This
    represents a trade-off between the efficiency of the deduplication
    (fewer bits means better deduplication) as compared to the amount
    of metadata to keep on disk and the RAM usage during repo
    operations (more bits means fewer objects, means less metadata
    space and RAM use).  The expected average block size is 2^bits (1
    << bits). A sufficiently small change in a file would cause that
    much new data to be saved (plus tree metadata). The maximum blob
    size is four times that.

    `legacy` refers to the current split method, which has an
    unintentional quirk where it "skips a bit".

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
