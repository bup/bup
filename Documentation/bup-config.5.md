% bup-config(5) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-config - bup configuration options

# DESCRIPTION

`bup` specific options may be set in the relevant `git` config
(`git-config(1)`), and `bup` also respects some existing `git`
options.

# OPTIONS

bup.split-trees
:   When this boolean option is set to true, `bup` will attempt to
    split trees (directories) when writing to the repository during,
    for example `bup save ...`, `bup gc ..`, etc.  This can notably
    decrease the size of the new data added to the repository when
    large directories have changed (e.g. large active Maildirs).  See
    "Handling large directories" in the DESIGN in the `bup` source for
    additional information.

pack.packSizeLimit
:   Respected when writing pack files (e.g. via `bup save ...`).

# SEE ALSO

`git-config`(1)

# BUP

Part of the `bup`(1) suite.
