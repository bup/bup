% bup-fuse(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-fuse - mount a bup repository as a filesystem

# SYNOPSIS

bup fuse [-d] [-f] [-o] \<mountpoint\>

# DESCRIPTION

`bup fuse` opens a bup repository and exports it as a
`fuse`(7) userspace filesystem.

This feature is only available on systems (such as Linux)
which support FUSE.

**WARNING**: bup fuse is still experimental and does not
enforce any file permissions!  All files will be readable
by all users.

When you're done accessing the mounted fuse filesystem, you
should unmount it with `umount`(8).

# OPTIONS

-d, \--debug
:   run in the foreground and print FUSE debug information
    for each request.

-f, \--foreground
:   run in the foreground and exit only when the filesystem
    is unmounted.

-o, \--allow-other
:   permit other users to access the filesystem. Necessary for
    exporting the filesystem via Samba, for example.

# EXAMPLES
    rm -rf /tmp/buptest
    mkdir /tmp/buptest
    sudo bup fuse -d /tmp/buptest
    ls /tmp/buptest/*/latest
    ...
    umount /tmp/buptest

# SEE ALSO

`fuse`(7), `fusermount`(1), `bup-ls`(1), `bup-ftp`(1),
`bup-restore`(1), `bup-web`(1)

# BUP

Part of the `bup`(1) suite.
