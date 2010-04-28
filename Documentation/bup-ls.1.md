% bup-ls(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-ls - list the contents of a bup repository

# SYNOPSIS

bup ls [-s] <paths...>

# DESCRIPTION

`bup ls` lists files and directories in your bup repository
using the same directory hierarchy as they would have with
`bup-fuse`(1).

The top level directory is the branch (corresponding to
the `-n` option in `bup save`), the next level is the date
of the backup, and subsequent levels correspond to files in
the backup.

Once you have identified the file you want using `bup ls`,
you can view its contents using `bup join` or `git show`.

# OPTIONS

-s, --hash
:   show hash for each file/directory.


# EXAMPLE

    bup ls /myserver/latest/etc/profile

# SEE ALSO

`bup-join`(1), `bup-fuse`(1), `bup-ftp`(1), `bup-save`(1), `git-show`(1)

# BUP

Part of the `bup`(1) suite.
