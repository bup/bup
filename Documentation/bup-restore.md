% bup-restore(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-restore - extract files from a backup set

# SYNOPSIS

bup restore [\--outdir=*outdir*] [-v] [-q] \<paths...\>;

# DESCRIPTION

`bup restore` extracts files from a backup set (created
with `bup-save`(1)) to the local filesystem.

The specified *paths* are of the form
/_branch_/_revision_/_path/to/file_.  The components of the
path are as follows:

branch
:   the name of the backup set to restore from; this
    corresponds to the `--name` (`-n`) option to `bup save`.

revision
:   the revision of the backup set to restore.  The
    revision *latest* is always the most recent
    backup on the given branch.  You can discover other
    revisions using `bup ls /branch`.
    
/path/to/file
:   the original absolute filesystem path to the file you
    want to restore.  For example, `/etc/passwd`.
    
Note: if the /path/to/file is a directory, `bup restore`
will restore that directory as well as recursively
restoring all its contents.

If /path/to/file is a directory ending in a slash (ie.
/path/to/dir/), `bup restore` will restore the children of
that directory directly to the current directory (or the
`--outdir`).  If the directory does *not* end in a slash,
the children will be restored to a subdirectory of the
current directory.  See the EXAMPLES section to see how
this works.

Whenever path metadata is available, `bup restore` will attempt to
restore it.  When restoring ownership, bup implements tar/rsync-like
semantics.  It will not try to restore the user unless running as
root, and it will fall back to the numeric uid or gid whenever the
metadata contains a user or group name that doesn't exist on the
current system.  The use of user and group names can be disabled via
`--numeric-ids` (which can be important when restoring a chroot, for
example), and as a special case, a uid or gid of 0 will never be
remapped by name.

Hardlinks will also be restored when possible, but at least currently,
no links will be made to targets outside the restore tree, and if the
restore tree spans a different arrangement of filesystems from the
save tree, some hardlink sets may not be completely restored.

Also note that changing hardlink sets on disk between index and save
may produce unexpected results.  With the current implementation, bup
will attempt to recreate any given hardlink set as it existed at index
time, even if all of the files in the set weren't still hardlinked
(but were otherwise identical) at save time.

Note that during the restoration process, access to data within the
restore tree may be more permissive than it was in the original
source.  Unless security is irrelevant, you must restore to a private
subdirectory, and then move the resulting tree to its final position.
See the EXAMPLES section for a demonstration.

# OPTIONS

-C, \--outdir=*outdir*
:   create and change to directory *outdir* before
    extracting the files.

\--numeric-ids
:   restore numeric IDs (user, group, etc.) rather than names.

-v, \--verbose
:   increase log output.  Given once, prints every
    directory as it is restored; given twice, prints every
    file and directory.

-q, \--quiet
:   don't show the progress meter.  Normally, is stderr is
    a tty, a progress display is printed that shows the
    total number of files restored.

# EXAMPLE
    
Create a simple test backup set:
    
    $ bup index -u /etc
    $ bup save -n mybackup /etc/passwd /etc/profile
    
Restore just one file:
    
    $ bup restore /mybackup/latest/etc/passwd
    Restoring: 1, done.
    
    $ ls -l passwd
    -rw-r--r-- 1 apenwarr apenwarr 1478 2010-09-08 03:06 passwd
    
Restore the whole directory (no trailing slash):
    
    $ bup restore -C test1 /mybackup/latest/etc
    Restoring: 3, done.
    
    $ find test1
    test1
    test1/etc
    test1/etc/passwd
    test1/etc/profile
    
Restore the whole directory (trailing slash):
    
    $ bup restore -C test2 /mybackup/latest/etc/
    Restoring: 2, done.
    
    $ find test2
    test2
    test2/passwd
    test2/profile

Restore a tree without risk of unauthorized access:

    # mkdir --mode 0700 restore-tmp

    # bup restore -C restore-tmp /somebackup/latest/foo
    Restoring: 42, done.

    # mv restore-tmp/foo somewhere

    # rmdir restore-tmp
    

# SEE ALSO

`bup-save`(1), `bup-ftp`(1), `bup-fuse`(1), `bup-web`(1)

# BUP

Part of the `bup`(1) suite.
