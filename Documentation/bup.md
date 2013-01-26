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

The individual bup subcommands appear in their own man
pages.

# GLOBAL OPTIONS

\--version
:   print bup's version number.  Equivalent to
    `bup-version`(1)

-d, \--bup-dir=*BUP_DIR*
:   use the given BUP_DIR parameter as the bup repository
    location, instead of reading it from the $BUP_DIR
    environment variable or using the default `~/.bup`
    location.


# COMMONLY USED SUBCOMMANDS

`bup-fsck`(1)
:   Check backup sets for damage and add redundancy information
`bup-ftp`(1)
:   Browse backup sets using an ftp-like client
`bup-fuse`(1)
:   Mount your backup sets as a filesystem
`bup-help`(1)
:   Print detailed help for the given command
`bup-index`(1)
:   Create or display the index of files to back up
`bup-on`(1)
:   Backup a remote machine to the local one
`bup-restore`(1)
:   Extract files from a backup set
`bup-save`(1)
:   Save files into a backup set (note: run "bup index" first)
`bup-web`(1)
:   Launch a web server to examine backup sets


# RARELY USED SUBCOMMANDS

`bup-damage`(1)
:   Deliberately destroy data
`bup-drecurse`(1)
:   Recursively list files in your filesystem
`bup-init`(1)
:   Initialize a bup repository
`bup-join`(1)
:   Retrieve a file backed up using `bup-split`(1)
`bup-ls`(1)
:   Browse the files in your backup sets
`bup-margin`(1)
:   Determine how close your bup repository is to armageddon
`bup-memtest`(1)
:   Test bup memory usage statistics
`bup-midx`(1)
:   Index objects to speed up future backups
`bup-newliner`(1)
:   Make sure progress messages don't overlap with output
`bup-random`(1)
:   Generate a stream of random output
`bup-server`(1)
:   The server side of the bup client-server relationship
`bup-split`(1)
:   Split a single file into its own backup set
`bup-tick`(1)
:   Wait for up to one second.
`bup-version`(1)
:   Report the version number of your copy of bup.


# SEE ALSO

`git`(1) and the *README* file from the bup distribution.

The home of bup is at <http://github.com/bup/bup/>.
