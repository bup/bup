% bup-init(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-init - initialize a bup repository

# SYNOPSIS

[BUP_DIR=*localpath*] bup init [-r *host*:*path*]

# DESCRIPTION

`bup init` initializes a repository.  The location will be the
directory specifed by any global `-d` argument (see `bup`(1)), the
value of `BUP_DIR` in the environment if set, or `~/.bup`.

# OPTIONS

-r, \--remote=*host*:[*path*]
:   Initialize not only the local repository, but also the remote
    repository given by the *host* and *path*.  If *path* is omitted ,
    it will be the value of `BUP_DIR` in the remote environment if
    set, or `~/.bup` in the remote filesystem.  The connection to the
    remote server is made with SSH.  If you'd like to specify which
    port, user or private key to use for the SSH connection, we
    recommend you use the `~/.ssh/config` file (`ssh_config(5)`).

# EXAMPLES
    bup init
    

# SEE ALSO

`bup-fsck`(1), `ssh_config`(5)

# BUP

Part of the `bup`(1) suite.
