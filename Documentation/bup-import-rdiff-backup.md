% bup-import-rdiff-backup(1) Bup %BUP_VERSION%
% Zoran Zaric <zz@zoranzaric.de>
% %BUP_DATE%

# NAME

bup-import-rdiff-backup - import a rdiff-backup archive

# SYNOPSIS

bup import-rdiff-backup [-n] <path to rdiff-backup root> <backup name>

# DESCRIPTION

`bup import-rdiff-backup` imports a rdiff-backup archive. The
timestamps for the backups are preserved and the path to
the rdiff-backup archive is stripped from the paths.

# OPTIONS

-n,--dry-run
:   don't do anything just print out what would be done

# EXAMPLES

    $ bup import-rdiff-backup /.snapshots legacy-rdiff-backup

# BUP

Part of the `bup`(1) suite.
