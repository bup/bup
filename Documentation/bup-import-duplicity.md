% bup-import-duplicity(1) Bup %BUP_VERSION%
% Zoran Zaric <zz@zoranzaric.de>
% %BUP_DATE%

# NAME

bup-import-duplicity - import a duplicity archive

# SYNOPSIS

bup import-duplicity [-n] <duplicity target url> <backup name>

# DESCRIPTION

`bup import-duplicity` imports a duplicity archive. The
timestamps for the backups are preserved and the path to
the duplicity archive is stripped from the paths.

# OPTIONS

-n,--dry-run
:   don't do anything just print out what would be done

# EXAMPLES

    $ bup import-duplicty file:///DUPLICITY legacy-duplicity

# BUP

Part of the `bup`(1) suite.
