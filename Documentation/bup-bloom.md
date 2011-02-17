% bup-bloom(1) Bup %BUP_VERSION%
% Brandon Low <lostlogic@lostlogicx.com>
% %BUP_DATE%

# NAME

bup-bloom - generates, regenerates, updates bloom filters

# SYNOPSIS

bup daemon [-d dir] [-o outfile] [-k hashes]

# DESCRIPTION

`bup bloom` builds a bloom filter file for a bup
repository. If one already exists, it checks the filter and
updates or regenerates it as needed.

# OPTIONS

-f, --force
:   don't update the existing bloom file; generate a new
    one from scratch.

-d, --dir=*directory*
:   the directory, containing .idx files, to process.
    Defaults to $BUP_DIR/objects/pack

-o, --outfile=*outfile*
:   the file to write the bloom filter to.  defaults to
    $dir/bup.bloom

-k, --hashes=*hashes*
:   number of hash functions to use only 4 and 5 are valid.
    defaults to 5 for repositories < 2 TiB, or 4 otherwise.
    See comments in git.py for more on this value.

# BUP

Part of the `bup`(1) suite.
