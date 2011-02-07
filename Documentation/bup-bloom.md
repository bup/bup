% bup-bloom(1) Bup %BUP_VERSION%
% Brandon Low <lostlogic@lostlogicx.com>
% %BUP_DATE%

# NAME

bup-bloom - generates, regenerates, updates bloom filters

# SYNOPSIS

bup daemon [-d dir] [-o outfile]

# DESCRIPTION

`bup bloom` builds a bloom filter file for a bup repo, if
one already exists, it checks it and updates or regenerates
it if needed.

# OPTIONS

-d, --dir=*directory*
:   the directory, containing .idx files, to process.
    defaults to $BUP_DIR/objects/pack

-o, --outfile=*outfile*
:   the file to write the bloom filter to.
    defaults to $dir/bup.bloom

# BUP

Part of the `bup`(1) suite.
