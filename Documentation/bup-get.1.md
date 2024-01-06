% bup-get(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-get - copy repository items (CAUTION: EXPERIMENTAL)

# SYNOPSIS

bup get \[-s *source-path*\] \[-r *host*:*path*\]  OPTIONS \<(METHOD *ref* [*dest*])\>...

# DESCRIPTION

`bup get` copies the indicated *ref*s from the source repository to
the destination repository (respecting `--bup-dir` and `BUP_DIR`),
according to the specified METHOD, which may be one of `--ff`,
`--ff:`, `--append`, `--append:`, `--pick`, `--pick:`, `--force-pick`,
`--force-pick:`, `--new-tag`, `--new-tag:`, `--replace`, `--replace:`,
or `--unnamed`.  See the EXAMPLES below for a quick introduction.

The *ref* is the source repository reference of the object to be
fetched, and the *dest* is the optional destination reference.  A
*dest* may only be specified for a METHOD whose name ends in a colon.
For example:

    bup get -s /source/repo --ff foo
    bup get -s /source/repo --ff: foo/latest bar
    bup get -s /source/repo --pick: foo/2010-10-10-101010 .tag/bar

As a special case, if *ref* names the "latest" save symlink, then bup
will act exactly as if the save that "latest" points to had been
specified, rather than the "latest" symlink itself, so `bup get
foo/latest` will actually be interpreted as something like `bup get
foo/2013-01-01-030405`.

In some situations `bup get` will evaluate a branch operation
according to whether or not it will be a "fast-forward" (which
requires that any existing destination branch be an ancestor of the
source).

An existing destination tag can only be overwritten by a `--replace`
or `--force-pick`.

When a new commit is created (i.e. via `--append`, `--pick`, etc.), it
will have the same author, author date, and message as the original,
but a committer and committer date corresponding to the current user
and time.

If requested by the appropriate options, bup will print the commit,
tree, or tag hash for each destination reference updated.  When
relevant, the tree hash will be printed before the commit hash.

Local *ref*s can be pushed to a remote repository with the `--remote`
option, and remote *ref*s can be pulled into a local repository via
"bup on HOST get ...".  See `bup-on`(1) and the EXAMPLES below for
further information.

WARNING: This is one of the few bup commands that can modify your
archives in intentionally destructive ways.  Though if an attempt to
join or restore the data you still care about succeeds after you've
run this command, then that's a fairly encouraging sign that it worked
correctly.  (The dev/compare-trees command in the source tree can be
used to help test before/after results.)

# METHODS

\--ff *ref*, \--ff: *ref* *dest*
:   fast-forward *dest* to match *ref*.  If *dest* is not specified
    and *ref* names a save, set *dest* to the save's branch.  If
    *dest* is not specified and *ref* names a branch or a tag, use the
    same name for *dest*.

\--append *ref*, \--append: *ref* *dest*
:   append all of the commits represented by *ref* to *dest* as new
    commits.  If *ref* names a directory/tree, append a new commit for
    that tree.  If *dest* is not specified and *ref* names a save or
    branch, set *dest* to the *ref* branch name.  If *dest* is not
    specified and *ref* names a tag, use the same name for *dest*.

\--pick *ref*, \--pick: *ref* *dest*
:   append the single commit named by *ref* to *dest* as a new commit.
    If *dest* is not specified and *ref* names a save, set *dest* to
    the *ref* branch name.  If *dest* is not specified and *ref* names
    a tag, use the same name for *dest*.

\--force-pick *ref*, \--force-pick: *ref* *dest*
:   do the same thing as `--pick`, but don't refuse to overwrite an
    existing tag.

\--new-tag *ref*, \--new-tag: *ref* *dest*
:   create a *dest* tag for *ref*, but refuse to overwrite an existing
    tag.  If *dest* is not specified and *ref* names a tag, use the
    same name for *dest*.

\--replace *ref*, \--replace: *ref* *dest*
:   clobber *dest* with *ref*, overwriting any existing tag, or
    replacing any existing branch.  If *dest* is not specified and
    *ref* names a branch or tag, use the same name for *dest*.

\--unnamed *ref*
:   copy *ref* into the destination repository, without any name,
    leaving a potentially dangling reference until/unless the object
    named by *ref* is referred to some other way (cf. `bup tag`).

# OPTIONS

-s, \--source=*path*
:   use *path* as the source repository, instead of the default.

-r, \--remote=*host*:*path*
:   store the indicated items on the given remote server.  If *path*
    is omitted, uses the default path on the remote server (you still
    need to include the ':').  The connection to the remote server is
    made with SSH.  If you'd like to specify which port, user or
    private key to use for the SSH connection, we recommend you use
    the `~/.ssh/config` file.

-c, \--print-commits
:   for each updated branch, print the new git commit id.

-t, \--print-trees
:   for each updated branch, print the new git tree id of the
    filesystem root.

\--print-tags
:   for each updated tag, print the new git id.

-v, \--verbose
:   increase verbosity (can be used more than once).  With
    `-v`, print the name of every item fetched, with `-vv` add
    directory names, and with `-vvv` add every filename.

\--bwlimit=*bytes/sec*
:   don't transmit more than *bytes/sec* bytes per second to the
    server.  This can help avoid sucking up all your network
    bandwidth.  Use a suffix like k, M, or G to specify multiples of
    1024, 1024\*1024, 1024\*1024\*1024 respectively.

-*#*, \--compress=*#*
:   set the compression level to # (a value from 0-9, where
    9 is the highest and 0 is no compression).  The default
    is 1 (fast, loose compression)

# EXAMPLES

    # Update or copy the archives branch in src-repo to the local repository.
    $ bup get -s src-repo --ff archives

    # Append a particular archives save to the pruned-archives branch.
    $ bup get -s src-repo --pick: archives/2013-01-01-030405 pruned-archives

    # Update or copy the archives branch on remotehost to the local
    # repository.
    $ bup on remotehost get --ff archives

    # Update or copy the local branch archives to remotehost.
    $ bup get -r remotehost: --ff archives

    # Update or copy the archives branch in src-repo to remotehost.
    $ bup get -s src-repo -r remotehost: --ff archives

    # Update the archives-2 branch on remotehost to match archives.
    # If archives-2 exists and is not an ancestor of archives, bup
    # will refuse.
    $ bup get -r remotehost: --ff: archives archives-2

    # Replace the contents of branch y with those of x.
    $ bup get --replace: x y

    # Copy the latest local save from the archives branch to the
    # remote tag foo.
    $ bup get -r remotehost: --pick: archives/latest .tag/foo

    # Or if foo already exists:
    $ bup get -r remotehost: --force-pick: archives/latest .tag/foo

    # Append foo (from above) to the local other-archives branch.
    $ bup on remotehost get --append: .tag/foo other-archives

    # Append only the /home directory from archives/latest to only-home.
    $ bup get -s "$BUP_DIR" --append: archives/latest/home only-home

# SEE ALSO

`bup-on`(1), `bup-tag`(1), `ssh_config`(5)

# BUP

Part of the `bup`(1) suite.
