% bup-init(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-init - initialize a bup repository

# SYNOPSIS

bup init [-r *host*:*path*] [*directory*]

# DESCRIPTION

`bup init` initializes a repository.  The location will be the
`*directory*` if provided, the directory specifed by any global `-d`
argument (see `bup`(1)), the value of `BUP_DIR` in the environment if
set, or `~/.bup`.

# OPTIONS

-r, \--remote=[*user*@]*host*:[*path*], \--remote=URL
:   Initialize not only the local repository, but also the specified
    remote repository.  This is not necessary if you intend to use the
    default location on the server (ie. with no *path*).  By default
    the connection to the remote server is made with SSH.  See bup(1)
    REMOTE OPTIONS for further information.

# EXAMPLES
    bup init ~/archive
    
# SEE ALSO

`bup-fsck`(1), `ssh_config`(5)

# BUP

Part of the `bup`(1) suite.
