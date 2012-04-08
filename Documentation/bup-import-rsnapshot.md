% bup-import-rsnapshot(1) Bup %BUP_VERSION%
% Zoran Zaric <zz@zoranzaric.de>
% %BUP_DATE%

# NAME

bup-import-rsnapshot - import a rsnapshot archive

# SYNOPSIS

bup import-rsnapshot [-n] \<path to snapshot_root\> [\<backuptarget\>]

# SYNOPSIS

`bup import-rsnapshot` imports an rsnapshot archive. The
timestamps for the backups are preserved and the path to
the rsnapshot archive is stripped from the paths.

`bup import-rsnapshot` either imports the whole archive
or imports all backups only for a given backuptarget.

# OPTIONS

-n, \--dry-run
:   don't do anything just print out what would be done

# EXAMPLES

    $ bup import-rsnapshot /.snapshots

    $ bup import-rsnapshot /.snapshots host1

# BUP

Part of the `bup`(1) suite.
