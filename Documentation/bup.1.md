% bup(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup - Backup program using rolling checksums and git file formats

# SYNOPSIS

bup [global options...] \<command\> [options...]

# DESCRIPTION

`bup` is a program for making backups of your files using
the git file format.

Unlike `git`(1) itself, bup is
optimized for handling huge data sets including individual
very large files (such a virtual machine images).  However,
once a backup set is created, it can still be accessed
using git tools.

Subcommands are described in separate man pages.  For example
`bup-init`(1) covers `bup init`.

# GLOBAL OPTIONS

\--version
:   print bup's version number.  Equivalent to `bup version`.

-d, \--bup-dir=*BUP_DIR*
:   use the given BUP_DIR parameter as the bup repository
    location, instead of reading it from the $BUP_DIR
    environment variable or using the default `~/.bup`
    location.

# PRIMARY COMMANDS

`bup-init`(1)
:   Initialize a bup repository

`bup-index`(1)
:   Create or display the index of files to back up

`bup-save`(1)
:   Save files into a backup set (note: run "bup index" first)

`bup-restore`(1)
:   Extract files from a backup set

`bup-fsck`(1)
:   Check backup sets for damage and add recovery information

`bup-on`(1)
:   Index/save/split/get/... a remote machine

`bup-help`(1)
:   Print detailed help for the given command

# INSPECTION COMMANDS

`bup-ls`(1)
:   Browse the files in your backup sets

`bup-fuse`(1)
:   Mount your backup sets as a filesystem

`bup-web`(1)
:   Launch a web server to examine backup sets

`bup-ftp`(1)
:   Browse backup sets using an ftp-like client

# MANIPULATION COMMANDS

`bup-gc`(1)
:   Remove unreferenced, unneeded data

`bup-get`(1)
:   Transfer/transform items between/within repositories

`bup-prune-older`(1)
:   Remove older saves

`bup-rm`(1)
:   Remove references to archive content

# IMPORT COMMANDS

`bup-import-duplicity`(1)
:   Import from `duplicity`(1)

`bup-import-rdiff-backup`(1)
:   Import from `rdiff-backup`(1)

`bup-import-rsnapshot`(1)
:   Import from `rsnapshot`(1)

# OTHER COMMANDS

`bup-cat-file`(1)
:   Extract archive content

`bup-drecurse`(1)
:   Recursively list files in your filesystem

`bup-features`(1)
:   Report the current status and capabilities of bup itself

`bup-join`(1)
:   Retrieve a file backed up using `bup-split`(1)

`bup-server`(1)
:   The server side of the bup client-server relationship

`bup-split`(1)
:   Split a single file into its own backup set

`bup-tag`(1)
:   Tag a commit in the bup repository

`bup-validate-object-links`(1)
:   Scan the repository for broken object links

`bup-validate-ref-links`(1)
:   Check repository refs for links to missing objects

`bup-version`(1)
:   Report the version number of your copy of bup.

# ESOTERIC COMMANDS

`bup-bloom`(1)
:   Generates, regenerates, updates bloom filters

`bup-damage`(1)
:   Deliberately destroy data

`bup-margin`(1)
:   Determine how close your bup repository is to armageddon

`bup-memtest`(1)
:   Test bup memory usage statistics

`bup-meta`(1)
:   Create or extract a metadata archive

`bup-midx`(1)
:   Index objects to speed up future backups

`bup-random`(1)
:   Generate a stream of random output

`bup-tick`(1)
:   Wait for up to one second.

# ENVIRONMENT

`BUP_ASSUME_GIT_VERSION_IS_FINE`
:   If set to `true`, `yes`, or `1`, assume the version of `git`
    in the path is acceptable.

# SEE ALSO

The *README* file from the bup distribution, `git`(1), and
http://bup.github.io

