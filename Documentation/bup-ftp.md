% bup-ftp(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-ftp - ftp-like client for navigating bup repositories

# SYNOPSIS

bup ftp

# DESCRIPTION

`bup ftp` is a command-line tool for navigating bup
repositories.  It has commands similar to the Unix `ftp`(1)
command.  The file hierarchy is the same as that shown by
`bup-fuse`(1) and `bup-ls`(1).

Note: if your system has the python-readline library
installed, you can use the \<tab\> key to complete filenames
while navigating your backup data.  This will save you a
lot of typing.


# COMMANDS

The following commands are available inside `bup ftp`:

ls [-s] [-a] [*path*]
:   print the contents of a directory. If no path argument
    is given, the current directory's contents are listed.
    If -a is given, also include hidden files (files which
    start with a `.` character). If -s is given, each file
    is displayed with its hash from the bup archive to its
    left.

cd *dirname*
:   change to a different working directory

pwd
:   print the path of the current working directory

cat *filenames...*
:   print the contents of one or more files to stdout

get *filename* *localname*
:   download the contents of *filename* and save it to disk
    as *localname*.  If *localname* is omitted, uses
    *filename* as the local name.
    
mget *filenames...*
:   download the contents of the given *filenames* and
    stores them to disk under the same names.  The
    filenames may contain Unix filename globs (`*`, `?`,
    etc.)
    
help
:   print a list of available commands

quit
:   exit the `bup ftp` client


# EXAMPLE

    $ bup ftp
    bup> ls
    mybackup/    yourbackup/

    bup> cd mybackup/
    bup> ls
    2010-02-05-185507@   2010-02-05-185508@    latest@

    bup> cd latest/
    bup> ls
      (...etc...)

    bup> get myfile
    Saving 'myfile'
    bup> quit


# SEE ALSO

`bup-fuse`(1), `bup-ls`(1), `bup-save`(1), `bup-restore`(1)


# BUP

Part of the `bup`(1) suite.
