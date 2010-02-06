% bup(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup - Backup program using rolling checksums and git file formats

# SYNOPSIS

bup <command> [options...]

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

# COMMONLY USED SUBCOMMANDS

`bup-index`(1)
:   Manage the index of files to back up.
`bup-fsck`(1)
:   Verify or recover the bup repository.
`bup-fuse`(1)
:   Mount the bup repository as a filesystem.
`bup-save`(1)
:   Back up the files in the index.
`bup-split`(1)
:   Back up an individual file, such as a tarball.
`bup-join`(1)
:   Retrieve a file backed up using `bup-split`(1).
`bup-midx`(1)
:   Make backups go faster by generating midx files.

# RARELY USED SUBCOMMANDS

`bup-damage`(1)
:   Deliberately destroy data.
`bup-drecurse`(1)
:   Recursively list files in your filesystem.
`bup-init`(1)
:   Initialize a bup repository.
`bup-ls`(1)
:   List the files in a bup repository.
`bup-margin`(1)
:   Determine how close your bup repository is to armageddon.
`bup-server`(1)
:   The server side of the bup client-server relationship.
`bup-tick`(1)
:   Sleep for up to one second.

# SEE ALSO

`git`(1) and the *README* file from the bup distribution.

The home of bup is at <http://github.com/apenwarr/bup/>.
