% bup-ls(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-ls - list the contents of a bup repository

# SYNOPSIS

bup ls [OPTION...] \<paths...\>

# DESCRIPTION

`bup ls` lists files and directories in your bup repository
using the same directory hierarchy as they would have with
`bup-fuse`(1).

The top level directory contains the branch (corresponding to
the `-n` option in `bup save`), the next level is the date
of the backup, and subsequent levels correspond to files in
the backup.

When `bup ls` is asked to output on a tty, and `-l` is not specified,
it formats the output in columns so it can list as much as possible in
as few lines as possible. However, when `-l` is specified or bup is
asked to output to something other than a tty (say you pipe the output
to another command, or you redirect it to a file), it will print one
file name per line. This makes the listing easier to parse with
external tools.

Note that `bup ls` doesn't show hidden files by default and one needs to use
the `-a` option to show them. Files are hidden when their name begins with a
dot. For example, on the topmost level, the special directories named `.commit`
and `.tag` are hidden directories.

Once you have identified the file you want using `bup ls`,
you can view its contents using `bup join` or `git show`.

# OPTIONS

-s, \--hash
:   show hash for each file/directory.

-a, \--all
:   show hidden files.

-A, \--almost-all
:   show hidden files, except "." and "..".

-d, \--directory
:   show information about directories themselves, rather than their
    contents, and don't follow symlinks.

-l
:   provide a detailed, long listing for each item.

-F, \--classify
:   append type indicator: dir/, symlink@, fifo|, socket=, and executable*.

\--file-type
:   append type indicator: dir/, symlink@, fifo|, socket=.

\--human-readable
:   print human readable file sizes (i.e. 3.9K, 4.7M).

\--numeric-ids
:   display numeric IDs (user, group, etc.) rather than names.

# EXAMPLES
    bup ls /myserver/latest/etc/profile

    bup ls -a /

# SEE ALSO

`bup-join`(1), `bup-fuse`(1), `bup-ftp`(1), `bup-save`(1), `git-show`(1)

# BUP

Part of the `bup`(1) suite.
