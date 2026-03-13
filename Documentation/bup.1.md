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

# REMOTE OPTIONS

Some options (currently just `--remote`) allow the specification of a
remote path as either a URL (see `REPOSITORY URLS` below) or a
`[*user*@]*host*:[*path*]`.

For either format, when there is no path, the default path on the
server will be used, and SSH settings for the connection can be
provided by a custom host to your `~/.ssh/config` file
(`ssh_config(5)`).

The argument is treated as a URL if it begins with a syntactically
valid URL scheme prefix that contains an "authority" (meaning that it
begins with `SCHEME://` as `ssh://...`  does), and the scheme must be
either `ssh` or `bup`; others will be rejected.

For the `[*user*@]*host*:[*path*]` syntax, if there is an @ symbol,
then everything before the rightmost @ is included in the *user* so
`-r x@y@z` indicates user `x@y`, host `z`.  The *host* must always be
followed by a colon, and anything after the first colon is the *path*.

For fully general purposes, prefer URLs to `[*user*@]*host*:[*path*]`,
so that there is no potential ambiguity.  For example, consider the
(unlikely) case where `ssh://x/y` is generated for a host named `ssh`
and path `//x/y`, which would be interpreted as a URL with host `x`
and path `/y`.

# REPOSITORY URLS

Bup supports the following URL schemes (i.e. `scheme:`) for referring
to a repository.  Note that the term "authority" below just means the
URL section after the `scheme://` and before the path, for example the
"user@host:port" of an SSH URL.

As an exception to the standard, a scheme may be "path-oriented",
which means that there is no separate query or fragment.  Anything
after the (optional) authority is taken as the "path" and the
constituent bytes are not decoded (e.g. percent decoded).  This allows
URLs provided on the command line to work naturally.  So
`ssh://host/x?z` has a path of `/x?z`.

`ssh:`
:   A path-oriented scheme (see above) that specifies access to a
    repository via a `bup-server(1)` launched on a host via SSH.  This
    scheme has syntax and semantics matching a typical `ssh:` URL,
    including support for a user and port
    (e.g. `ssh://user@host:2222/some/repo`), and the user and host can
    be percent encoded.

    As an extension to the standard, because URLs with an authority
    cannot specify a relative path when there's an authority, a
    leading `/./` is taken to indicate a relative path.  So
    `ssh://host/./x` indicates the path `x`.

`bup:`
:   Specifies a direct network connection to to an existing
    `bup-server(1)`.  Otherwise identical to `ssh:`, except that it
    does not support a user.

`file:`
:   A path-oriented scheme (see above) that specifies a repository's
    filesystem path.  This scheme has syntax and semantics matching a
    typical `file:` URL, except that it does not allow an authority
    (i.e. user, host, etc.).  So when constructing a URL from an
    arbitrary PATH, you can use `file:PATH` if the path starts with
    `///`, if it is a single character, or if the second character is
    not `/`.  Otherwise use `file://PATH` after ensuring the path is
    absolute, or dot-encoding it.

# ENVIRONMENT

`BUP_ASSUME_GIT_VERSION_IS_FINE`
:   If set to `true`, `yes`, or `1`, assume the version of `git`
    in the path is acceptable.

# SEE ALSO

The *README* file from the bup distribution, `git`(1), and
http://bup.github.io

