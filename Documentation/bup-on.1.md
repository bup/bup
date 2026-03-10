% bup-on(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-on - run a bup on a remote host, communicating with a local server

# SYNOPSIS

bup on [*user*@]*host*[:*port*] index ...  
bup on [*user*@]*host*[:*port*] save ...  
bup on [*user*@]*host*[:*port*] restore ...  
bup on [*user*@]*host*[:*port*] split ...  
bup on [*user*@]*host*[:*port*] version ...  
bup on [*user*@]*host*[:*port*] features ...  
bup on [*user*@]*host*[:*port*] help ...  

bup on [*user*@]*host*[:*port*] get ...  
(Prefer `bup get --source-url ssh://<hostname>...`)

# DESCRIPTION

`bup on` runs the command on the remote host via ssh, connected to a
bup server running on the local machine, so that remote commands like
`bup save` can back up to the local repository.  See `bup-index`(1),
`bup-save`(1), and so on for the command details.

Note that you don't need to (and shouldn't) provide a `--remote`
option.  This "reverse mode" is useful when the machine being backed
up isn't supposed to be able to ssh into the backup server.  Instead,
the backup server, even if hidden behind a one-way firewall on a
private or dynamic IP address, can connect to each of your important
machines using an ssh key, and initiate a backup that saves the remote
data to the local repository.

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

`bup-index`(1), `bup-save`(1), `bup-split`(1), `bup-get`(1)

# BUP

Part of the `bup`(1) suite.
