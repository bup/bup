% bup-meta(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-meta - create or extract a metadata archive

# SYNOPSIS

bup meta \--create
  ~ [-R] [-v] [-q] [\--no-symlinks] [\--no-paths] [-f *file*] \<*paths*...\>
  
bup meta \--list
  ~ [-v] [-q] [-f *file*]
  
bup meta \--extract
  ~ [-v] [-q] [\--numeric-ids] [\--no-symlinks] [-f *file*]
  
bup meta \--start-extract
  ~ [-v] [-q] [\--numeric-ids] [\--no-symlinks] [-f *file*]
  
bup meta \--finish-extract
  ~ [-v] [-q] [\--numeric-ids] [-f *file*]

bup meta \--edit
  ~ [\--set-uid *uid* | \--set-gid *gid* | \--set-user *user* | \--set-group *group* | ...] \<*paths*...\>

# DESCRIPTION

`bup meta` creates, extracts, or otherwise manipulates metadata
archives.  A metadata archive contains the metadata information
(timestamps, ownership, access permissions, etc.) for a set of
filesystem paths.

See `bup-restore`(1) for a description of the way ownership metadata
is restored.

# OPTIONS

-c, \--create
:   Create a metadata archive for the specified *path*s.  Write the
    archive to standard output unless `--file` is specified.

-t, \--list
:   Display information about the metadata in an archive.  Read the
    archive from standard input unless `--file` is specified.

-x, \--extract
:   Extract a metadata archive.  Conceptually, perform `--start-extract`
    followed by `--finish-extract`.  Read the archive from standard input
    unless `--file` is specified.

\--start-extract
:   Build a filesystem tree matching the paths stored in a metadata
    archive.  By itself, this command does not produce a full
    restoration of the metadata.  For a full restoration, this command
    must be followed by a call to `--finish-extract`.  Once this
    command has finished, all of the normal files described by the
    metadata will exist and be empty.  Restoring the data in those
    files, and then calling `--finish-extract` should restore the
    original tree.  The archive will be read from standard input
    unless `--file` is specified.

\--finish-extract
:   Finish applying the metadata stored in an archive to the
    filesystem.  Normally, this command should follow a call to
    `--start-extract`.  The archive will be read from standard input
    unless `--file` is specified.

\--edit
:   Edit metadata archives.  The result will be written to standard
    output unless `--file` is specified.

-f, \--file=*filename*
:   Read the metadata archive from *filename* or write it to
    *filename* as appropriate.  If *filename* is "-", then read from
    standard input or write to standard output.

-R, \--recurse
:   Recursively descend into subdirectories during `--create`.

\--numeric-ids
:   Apply numeric IDs (user, group, etc.) rather than names during
    `--extract` or `--finish-extract`.

\--symlinks
:   Record symbolic link targets when creating an archive, or restore
    symbolic links when extracting an archive (during `--extract`
    or `--start-extract`).  This option is enabled by default.
    Specify `--no-symlinks` to disable it.

\--paths
:   Record pathnames when creating an archive.  This option is enabled
    by default.  Specify `--no-paths` to disable it.

\--set-uid=*uid*
:   Set the metadata uid to the integer *uid* during `--edit`.

\--set-gid=*gid*
:   Set the metadata gid to the integer *gid* during `--edit`.

\--set-user=*user*
:   Set the metadata user to *user* during `--edit`.

\--unset-user
:   Remove the metadata user during `--edit`.

\--set-group=*group*
:   Set the metadata user to *group* during `--edit`.

\--unset-group
:   Remove the metadata group during `--edit`.

-v, \--verbose
:   Be more verbose (can be used more than once).

-q, \--quiet
:   Be quiet.

# EXAMPLES

    # Create a metadata archive for /etc.
    $ bup meta -cRf etc.meta /etc
    bup: removing leading "/" from "/etc"

    # Extract the etc.meta archive (files will be empty).
    $ mkdir tmp && cd tmp
    $ bup meta -xf ../etc.meta
    $ ls
    etc

    # Restore /etc completely.
    $ mkdir tmp && cd tmp
    $ bup meta --start-extract -f ../etc.meta
    ...fill in all regular file contents using some other tool...
    $ bup meta --finish-extract -f ../etc.meta

    # Change user/uid to root.
    $ bup meta --edit --set-uid 0 --set-user root \
        src.meta > dest.meta

# BUGS

Hard links are not handled yet.

# BUP

Part of the `bup`(1) suite.
