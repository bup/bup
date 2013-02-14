% bup-join(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-join - concatenate files from a bup repository

# SYNOPSIS

bup join [-r [*user*@]*host*:*path*] [refs or hashes...]

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

-r, \--remote=[*user*@]*host*:[*path*]
:   Retrieves objects from the given remote repository
    instead of the local one.  If *path* is omitted, uses the default 
    path on the remote server (you still need to include the ':').

-e, \--sshcmd="remote shell commandline"
:   allows the specification of an alternate remote shell command line for
    connecting to a server. A common use case is to specify optional parameters
    to the SSH command line. For example to use a custom port and key file:
        -e 'ssh -i /path/to/keyfile -p 22056'

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
