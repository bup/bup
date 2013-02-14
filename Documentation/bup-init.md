% bup-init(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-init - initialize a bup repository

# SYNOPSIS

[BUP_DIR=*localpath*] bup init [-r [*user*@]*host*:*path*]

# DESCRIPTION

`bup init` initializes your local bup repository.  You
usually don't need to run it unless you have set BUP_DIR
explicitly.  By default, BUP_DIR is `~/.bup` and will be
initialized automatically whenever you run any bup command.

# OPTIONS

-r, \--remote=[*user*@]*host*:*path*
:   Initialize not only the local repository, but also the
    remote repository given by *user*, *host* and *path*. *path* may be
    omitted if you intend to backup to the default path on the remote 
    server.
    
-e, \--sshcmd="remote shell commandline"
:   allows the specification of an alternate remote shell command line for
    connecting to a server. A common use case is to specify optional parameters
    to the SSH command line. For example to use a custom port and key file:
        -e 'ssh -i /path/to/keyfile -p 22056'

# EXAMPLE

    bup init
    

# SEE ALSO

`bup-fsck`(1), `ssh_config`(5)

# BUP

Part of the `bup`(1) suite.
