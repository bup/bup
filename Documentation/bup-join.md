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

-r, \--remote=*host*:*path*
:   Retrieves objects from the given remote repository
    instead of the local one. *path* may be blank, in which
    case the default remote repository is used.  The connection to the
    remote server is made with SSH.  If you'd like to specify which port, user
    or private key to use for the SSH connection, we recommend you use the
    `~/.ssh/config` file.


# EXAMPLE

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

`bup-split`(1), `bup-save`(1), `ssh_config`(5)

# BUP

Part of the `bup`(1) suite.
