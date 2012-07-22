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

Before trying to save files using `bup save`, you should
first update the index using `bup index`.  The reasons
for separating the two steps are described in the man page
for `bup-index`(1).

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
    `~/.bup/bupindex`.

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
    
    A directory */root/chroot/etc* saved with
    "bup save -n chroot \--strip /root/chroot" would be saved
    as */etc*.
    
\--strip-path=*path-prefix*
:   strips the given path prefix *path-prefix* from all
    files and directories.
    
    A directory */root/chroots/webserver* saved with
    "bup save -n webserver \--strip-path=/root/chroots" would
    be saved as */webserver/etc*
    
\--graft=*old_path*=*new_path*
:   a graft point *old_path*=*new_path* (can be used more than
    once).

    A directory */root/chroot/a/etc* saved with
    "bup save -n chroots \--graft /root/chroot/a/etc=/chroots/a"
    would be saved as */chroots/a/etc*

-*#*, \--compress=*#*
:   set the compression level to # (a value from 0-9, where
    9 is the highest and 0 is no compression).  The default
    is 1 (fast, loose compression)


# EXAMPLE

    $ bup index -ux /etc
    Indexing: 1981, done.

    $ bup save -r myserver: -n my-pc-backup --bwlimit=50k /etc
    Reading index: 1981, done.
    Saving: 100.00% (998/998k, 1981/1981 files), done.



    $ ls /home/joe/chroots/httpd
    bin var

    $ bup index -ux /home/joe/chroots/httpd
    Indexing: 1337, done.

    $ bup save --strip -n joes-httpd-chroot /home/joe/chroots/httpd
    Reading index: 1337, done.
    Saving: 100.00% (998/998k, 1337/1337 files), done.

    $ bup ls joes-httpd-chroot/latest/
    bin/
    var/


    $ bup save --strip-path=/home/joe/chroots -n joes-chroots \
         /home/joe/chroots/httpd
    Reading index: 1337, done.
    Saving: 100.00% (998/998k, 1337/1337 files), done.

    $ bup ls joes-chroots/latest/
    httpd/


    $ bup save --graft /home/joe/chroots/httpd=/http-chroot \
         -n joe
         /home/joe/chroots/httpd
    Reading index: 1337, done.
    Saving: 100.00% (998/998k, 1337/1337 files), done.

    $ bup ls joe/latest/
    http-chroot/


# SEE ALSO

`bup-index`(1), `bup-split`(1), `bup-on`(1),
`bup-restore`(1), `ssh_config`(5)

# BUP

Part of the `bup`(1) suite.
