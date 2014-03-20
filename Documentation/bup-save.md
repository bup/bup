% bup-save(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-save - create a new bup backup set

# SYNOPSIS

bup save [-r *host*:*path*] \<-t|-c|-n *name*\> [-#] [-f *indexfile*]
[-v] [-q] [\--smaller=*maxsize*] \<paths...\>;

# DESCRIPTION

`bup save` saves the contents of the given files or paths
into a new backup set and optionally names that backup set.

Note that in order to refer to your backup set later (i.e. for
restoration), you must either specify `--name` (the normal case), or
record the tree or commit id printed by `--tree` or `--commit`.

Before trying to save files using `bup save`, you should
first update the index using `bup index`.  The reasons
for separating the two steps are described in the man page
for `bup-index`(1).

By default, metadata will be saved for every path, and the metadata
for any unindexed parent directories of indexed paths will be taken
directly from the filesystem.  However, if `--strip`, `--strip-path`,
or `--graft` is specified, metadata will not be saved for the root
directory (*/*).  See `bup-restore`(1) for more information about the
handling of metadata.

# OPTIONS

-r, \--remote=*host*:*path*
:   save the backup set to the given remote server.  If
    *path* is omitted, uses the default path on the remote
    server (you still need to include the ':').  The connection to the
    remote server is made with SSH.  If you'd like to specify which port, user
    or private key to use for the SSH connection, we recommend you use the
    `~/.ssh/config` file.

-t, \--tree
:   after creating the backup set, print out the git tree
    id of the resulting backup.
    
-c, \--commit
:   after creating the backup set, print out the git commit
    id of the resulting backup.

-n, \--name=*name*
:   after creating the backup set, create a git branch
    named *name* so that the backup can be accessed using
    that name.  If *name* already exists, the new backup
    will be considered a descendant of the old *name*. 
    (Thus, you can continually create new backup sets with
    the same name, and later view the history of that
    backup set to see how files have changed over time.)

-d, \--date=*date*
:   specify the date of the backup, in seconds since the epoch, instead
    of the current time.

-f, \--indexfile=*indexfile*
:   use a different index filename instead of
    `$BUP_DIR/bupindex`.

-v, \--verbose
:   increase verbosity (can be used more than once).  With
    one -v, prints every directory name as it gets backed up.  With
    two -v, also prints every filename.

-q, \--quiet
:   disable progress messages.

\--smaller=*maxsize*
:   don't back up files >= *maxsize* bytes.  You can use
    this to run frequent incremental backups of your small
    files, which can usually be backed up quickly, and skip
    over large ones (like virtual machine images) which
    take longer.  Then you can back up the large files
    less frequently.  Use a suffix like k, M, or G to
    specify multiples of 1024, 1024*1024, 1024*1024*1024
    respectively.
    
\--bwlimit=*bytes/sec*
:   don't transmit more than *bytes/sec* bytes per second
    to the server.  This is good for making your backups
    not suck up all your network bandwidth.  Use a suffix
    like k, M, or G to specify multiples of 1024,
    1024*1024, 1024*1024*1024 respectively.
    
\--strip
:   strips the path that is given from all files and directories.
    
    A directory */root/chroot/etc* saved with "bup save -n chroot
    \--strip /root/chroot" would be saved as */etc*.  Note that
    currently, metadata will not be saved for the root directory (*/*)
    when this option is specified.
    
\--strip-path=*path-prefix*
:   strips the given path prefix *path-prefix* from all
    files and directories.
    
    A directory */root/chroot/webserver* saved with "bup save -n
    webserver \--strip-path=/root/chroot" would be saved as
    */webserver/etc*.  Note that currently, metadata will not be saved
    for the root directory (*/*) when this option is specified.
    
\--graft=*old_path*=*new_path*
:   a graft point *old_path*=*new_path* (can be used more than
    once).

    A directory */root/chroot/a/etc* saved with "bup save -n chroot
    \--graft /root/chroot/a=/chroot/a" would be saved as
    */chroot/a/etc*.  Note that currently, metadata will not be saved
    for the root directory (*/*) when this option is specified.

-*#*, \--compress=*#*
:   set the compression level to # (a value from 0-9, where
    9 is the highest and 0 is no compression).  The default
    is 1 (fast, loose compression)


# EXAMPLES
    $ bup index -ux /etc
    Indexing: 1981, done.

    $ bup save -r myserver: -n my-pc-backup --bwlimit=50k /etc
    Reading index: 1981, done.
    Saving: 100.00% (998/998k, 1981/1981 files), done.



    $ ls /home/joe/chroot/httpd
    bin var

    $ bup index -ux /home/joe/chroot/httpd
    Indexing: 1337, done.

    $ bup save --strip -n joes-httpd-chroot /home/joe/chroot/httpd
    Reading index: 1337, done.
    Saving: 100.00% (998/998k, 1337/1337 files), done.

    $ bup ls joes-httpd-chroot/latest/
    bin/
    var/


    $ bup save --strip-path=/home/joe/chroot -n joes-chroot \
         /home/joe/chroot/httpd
    Reading index: 1337, done.
    Saving: 100.00% (998/998k, 1337/1337 files), done.

    $ bup ls joes-chroot/latest/
    httpd/


    $ bup save --graft /home/joe/chroot/httpd=/http-chroot \
         -n joe
         /home/joe/chroot/httpd
    Reading index: 1337, done.
    Saving: 100.00% (998/998k, 1337/1337 files), done.

    $ bup ls joe/latest/
    http-chroot/


# SEE ALSO

`bup-index`(1), `bup-split`(1), `bup-on`(1),
`bup-restore`(1), `ssh_config`(5)

# BUP

Part of the `bup`(1) suite.
