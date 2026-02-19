% bup-join(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-join - concatenate files from a bup repository

# SYNOPSIS

bup join [-r *host*:*path*] [refs or hashes...]

# DESCRIPTION

`bup join` is roughly the opposite operation to
`bup-split`(1).  You can use it to retrieve the contents of
a file from a local or remote bup repository.

The supplied list of refs or hashes can be in any format
accepted by `git`(1), including branch names, commit ids,
tree ids, or blob ids.

If no refs or hashes are given on the command line, `bup
join` reads them from stdin instead.

# OPTIONS

-r, \--remote=[*user*@]*host*:[*path*], \--remote=URL
:   retrieve the data from the specified remote repository, by default
    via SSH.  See bup(1) REMOTE OPTIONS for further information.

# EXAMPLES
    # split and then rejoin a file using its tree id
    TREE=$(tar -cvf - /etc | bup split -t)
    bup join $TREE | tar -tf -
    
    # make two backups, then get the second-most-recent.
    # mybackup~1 is git(1) notation for the second most
    # recent commit on the branch named mybackup.
    tar -cvf - /etc | bup split -n mybackup
    tar -cvf - /etc | bup split -n mybackup
    bup join mybackup~1 | tar -tf -

# SEE ALSO

`bup-split`(1), `bup-save`(1), `bup-cat-file`, `ssh_config`(5)

# BUP

Part of the `bup`(1) suite.
