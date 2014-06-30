% bup-drecurse(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-drecurse - recursively list files in your filesystem

# SYNOPSIS

bup drecurse [-x] [-q] [\--exclude *path*]
\ [\--exclude-from *filename*] [\--exclude-rx *pattern*]
\ [\--exclude-rx-from *filename*] [\--profile] \<path\>

# DESCRIPTION

`bup drecurse` traverses files in the filesystem in a way
similar to `find`(1).  In most cases, you should use
`find`(1) instead.

This program is useful mainly for testing the file
traversal algorithm used in `bup-index`(1).

Note that filenames are returned in reverse alphabetical
order, as in `bup-index`(1).  This is important because you
can't generate the hash of a parent directory until you
have generated the hashes of all its children.  When
listing files in reverse order, the parent directory will
come after its children, making this easy.

# OPTIONS

-x, \--xdev, \--one-file-system
:   don't cross filesystem boundaries -- though as with tar and rsync,
    the mount points themselves will still be reported.

-q, \--quiet
:   don't print filenames as they are encountered.  Useful
    when testing performance of the traversal algorithms.

\--exclude=*path*
:   exclude *path* from the backup (may be repeated).

\--exclude-from=*filename*
:   read --exclude paths from *filename*, one path per-line (may be
    repeated).
    
\--exclude-rx=*pattern*
:   exclude any path matching *pattern*.  See `bup-index`(1) for
    details, but note that unlike index, drecurse will produce
    relative paths if the drecurse target is a relative path. (may be
    repeated).

\--exclude-rx-from=*filename*
:   read --exclude-rx patterns from *filename*, one pattern per-line
    (may be repeated).  Ignore completely empty lines.

\--profile
:   print profiling information upon completion.  Useful
    when testing performance of the traversal algorithms.
    
# EXAMPLES
    bup drecurse -x /

# SEE ALSO

`bup-index`(1)

# BUP

Part of the `bup`(1) suite.
