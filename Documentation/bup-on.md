% bup-on(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-on - run a bup server locally and client remotely

# SYNOPSIS

bup on \<hostname\> index ...

bup on \<hostname\> save ...

bup on \<hostname\> split ...


# DESCRIPTION

`bup on` runs the given bup command on the given host using
ssh.  It runs a bup server on the local machine, so that
commands like `bup save` on the remote machine can back up
to the local machine.  (You don't need to provide a
`--remote` option to `bup save` in order for this to work.)

See `bup-index`(1), `bup-save`(1), and so on for details of
how each subcommand works.

This 'reverse mode' operation is useful when the machine
being backed up isn't supposed to be able to ssh into the
backup server.  For example, your backup server can be
hidden behind a one-way firewall on a private or dynamic IP
address; using an ssh key, it can be authorized to ssh into
each of your important machines.  After connecting to each
destination machine, it initiates a backup, receiving the
resulting data and storing in its local repository.

For example, if you run several virtual private Linux
machines on a remote hosting provider, you could back them
up to a local (much less expensive) computer in your
basement.


# EXAMPLES

    # First index the files on the remote server
    
    $ bup on myserver index -vux /etc
    bup server: reading from stdin.
    Indexing: 2465, done.
    bup: merging indexes (186668/186668), done.
    bup server: done
    
    # Now save the files from the remote server to the
    # local $BUP_DIR
    
    $ bup on myserver save -n myserver-backup /etc
    bup server: reading from stdin.
    bup server: command: 'list-indexes'
    PackIdxList: using 7 indexes.
    Saving: 100.00% (241/241k, 648/648 files), done.    
    bup server: received 55 objects.
    Indexing objects: 100% (55/55), done.
    bup server: command: 'quit'
    bup server: done
    
    # Now we can look at the resulting repo on the local
    # machine
    
    $ bup ftp 'cat /myserver-backup/latest/etc/passwd'
    root:x:0:0:root:/root:/bin/bash
    daemon:x:1:1:daemon:/usr/sbin:/bin/sh
    bin:x:2:2:bin:/bin:/bin/sh
    sys:x:3:3:sys:/dev:/bin/sh
    sync:x:4:65534:sync:/bin:/bin/sync
    ...
    
# SEE ALSO

`bup-index`(1), `bup-save`(1), `bup-split`(1)

# BUP

Part of the `bup`(1) suite.
