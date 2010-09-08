% bup-save(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-save - create a new bup backup set

# SYNOPSIS

bup save [-r *host*:*path*] <-t|-c|-n *name*> [-v] [-q]
  [--smaller=*maxsize*] <paths...>

# DESCRIPTION

`bup save` saves the contents of the given files or paths
into a new backup set and optionally names that backup set.

Before trying to save files using `bup save`, you should
first update the index using `bup index`.  The reasons
for separating the two steps are described in the man page
for `bup-index`(1).

# OPTIONS

-r, --remote=*host*:*path*
:   save the backup set to the given remote server.  If
    *path* is omitted, uses the default path on the remote
    server (you still need to include the ':')

-t, --tree
:   after creating the backup set, print out the git tree
    id of the resulting backup.
    
-c, --commit
:   after creating the backup set, print out the git commit
    id of the resulting backup.

-n, --name=*name*
:   after creating the backup set, create a git branch
    named *name* so that the backup can be accessed using
    that name.  If *name* already exists, the new backup
    will be considered a descendant of the old *name*. 
    (Thus, you can continually create new backup sets with
    the same name, and later view the history of that
    backup set to see how files have changed over time.)
    
-v, --verbose
:   increase verbosity (can be used more than once).  With
    one -v, prints every directory name as it gets backed up.  With
    two -v, also prints every filename.

-q, --quiet
:   disable progress messages.

--smaller=*maxsize*
:   don't back up files >= *maxsize* bytes.  You can use
    this to run frequent incremental backups of your small
    files, which can usually be backed up quickly, and skip
    over large ones (like virtual machine images) which
    take longer.  Then you can back up the large files
    less frequently.  Use a suffix like k, M, or G to
    specify multiples of 1024, 1024*1024, 1024*1024*1024
    respectively.
    
--bwlimit=*bytes/sec*
:   don't transmit more than *bytes/sec* bytes per second
    to the server.  This is good for making your backups
    not suck up all your network bandwidth.  Use a suffix
    like k, M, or G to specify multiples of 1024,
    1024*1024, 1024*1024*1024 respectively.
    

# EXAMPLE
    
    $ bup index -ux /etc
    Indexing: 1981, done.
    
    $ bup save -r myserver: -n my-pc-backup --bwlimit=50k /etc
    Reading index: 1981, done.
    Saving: 100.00% (998/998k, 1981/1981 files), done.    
    

# SEE ALSO

`bup-index`(1), `bup-split`(1), `bup-on`(1),
`bup-restore`(1)

# BUP

Part of the `bup`(1) suite.
