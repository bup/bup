% bup-get(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-get - copy repository items (note CAUTION below)

# SYNOPSIS

bup get \[-s *source-path*\] \[-r *host*:*path*\]  OPTIONS \<(METHOD *ref* [*dest*])\>...

# DESCRIPTION

`bup get` transfers the indicated *ref*s from the source repository to
the destination repository (respecting `--bup-dir` and `BUP_DIR`),
according to the specified METHOD, which may be one of `--ff`,
`--ff:`, `--append`, `--append:`, `--pick`, `--pick:`, `--force-pick`,
`--force-pick:`, `--new-tag`, `--new-tag:`, `--replace`, `--replace:`,
or `--unnamed`.  By default it will `--copy` the data without
alteration, but it can also `--rewrite` it, potentially changing the
deduplication granularity, and `--repair` some kinds of damage. See
the EXAMPLES below for a quick introduction.

The *ref* is the source repository reference of the object to be
fetched, and the *dest* is the optional destination reference.  A
*dest* may only be specified for a METHOD whose name ends in a colon.
For example:

    bup get -s /source/repo --ff foo
    bup get -s /source/repo --ff: foo/latest bar
    bup get -s /source/repo --pick: foo/2010-10-10-101010 bar
    bup get -s /source/repo --pick: foo/2010-10-10-101010 .tag/bar

The behavior of any given METHOD is determined in part by the *ref*
and *dest* types, i.e. branch, save, tag, etc.

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

CAUTION: This is one of the few bup commands that can modify your
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
    existing tag, and if the tag refers to a commit, make it the
    parent of *ref*.

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
    named by *ref* is referred to some other way (cf. `bup
    tag`). Currently only compatible with `--copy`.

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

\--copy
:   copy the data without changes (i.e. without rewrites or
    repairs). This is the default.

\--rewrite
:   rewrite the data according to the destination repository
    configuration, e.g. its `bup.split.files`, and `bup.split.trees`
    values. Some incidental repairs may be performed during the
    transfer when they do not materially alter the result (see REPAIRS
    below).  Currently, `--rewrite`, `---repair`, or `--copy` must be
    specified whenever the source and destination repository
    configurations differ in a relevant way, and so far, `--rewrite`
    is only supported for appends and picks. This option is also
    contextual (see CONTEXTUAL OPTIONS). Note that rewriting a
    git-created save may, and for now will, introduce bup-related
    changes. Further, while tested, `--rewrite` is relatively new and
    so warrants even more caution (see CAUTION above) than `bup get`
    itself. Please consider validating the results carefully for now.

\--repair
:   in addition to what `--rewrite` does, perform all known repairs
    during the transfer. See REPAIRS below. This option is contextual
    (see CONTEXTUAL OPTIONS).

\--repair-id ID
:   set the repair session identifier, defaults to a UUID (v4). This
    identifier will be included in any `--repair`s made during the
    transfer. Currently, the identifier must be ASCII and must not
    include control characters or DEL (i.e. must be comprised of bytes
    \>= 20 and < 127). This option is contextual (see CONTEXTUAL
    OPTIONS).

\--ignore-missing
:   ignore missing objects encountered during a transfer.  Currently
    only supported by `--unnamed`, and potentially *dangerous*.

\--exclude-rx=*pattern*
:   exclude any path matching *pattern*, which must be a Python regular
    expression (http://docs.python.org/library/re.html).  The pattern
    will be compared against the full path, without anchoring, so
    "x/y" will match "ox/yard" or "box/yards".  To exclude the
    contents of /tmp, but not the directory itself, use
    "^/tmp/.". (may be repeated)

    Examples:

      * `/foo$` - exclude any file named foo
      * `/foo/$` - exclude any directory named foo
      * `/foo/.` - exclude the content of any directory named foo
      * `^/tmp/.` - exclude root-level tmp's content

    Only supported when rewriting or repairing. This option is
    contextual (see CONTEXTUAL OPTIONS).

\--exclude-rx-from=*filename*
:   read --exclude-rx patterns from *filename*, one pattern per-line
    (may be repeated).  Ignore completely empty lines. Only supported
    when rewriting. This option is contextual (see CONTEXTUAL
    OPTIONS).

\--no-excludes
:   forget any previous `--exclude-rx` or `--exclude-rx-from`
    options. This option is contextual (see CONTEXTUAL OPTIONS).

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
:   set the compression level to # (a value from 0-9, where 9 is the
    highest and 0 is no compression). Defaults to a configured
    pack.compression or core.compression, or 1 (fast, loose
    compression).

# CONTEXTUAL OPTIONS

Some options like `--repair` and `--ignore-missing` can differ across
METHODs, and each option changes the context for the next METHOD. So
you can have

    bup get ... --ignore-missing --unnamed REF \
        --no-ignore-missing --rewrite --append REF

Without `--no-ignore-missing` this command would fail because
`--ignore-missing` is incompatible with `--rewrite`.

Changing the currently active excludes is expensive because at the
moment the cache of remembered rewrites must be cleared whenever a
METHODs excludes differ from those for the previous METHOD.

# REPAIRS

`bup get` can fix (or mitigate) a number of known issues during the
transfer when `--repair` is requested, and a subset of "incidental"
repairs may also be performed during a `--rewrite`.

 * Versions of `bup` at or after 0.25 and before 0.30.1 might rarely
   drop metadata entries for non-directories (which can be detected by
   `bup-validate-refs`(1) `--bupm`). This makes the metadata for all
   of the other non-directory paths in the same directory unusable
   (ambiguous). When such an abridged `.bupm` is detected, `--repair`
   drops all of the `.bupm` entries except the one for the directory
   itself, ".", and so the affected paths lose most or all of their
   metadata (ownership, permissions, timestamps, etc.). These paths
   will have restrictive permissions (as if via umask 077) when
   presented, e.g. via `bup-restore(1)`, `bup-ls(1)`, etc.

 * Use of `bup get` or `bup gc` versions before 0.33.5 could cause
   repositories to end up with missing objects (which can be detected
   by `bup-validate-object-links`(1)). To fix affected trees,
   `--repair` substitutes synthesized "repair files" for any paths
   with missing objects. Note that there is currently no support for
   retrieving the unaffected parts of split files; the entire file is
   replaced with a repair file. These repair files contain the
   `--repair-id` and information about the replacement. Support for
   split trees was added after the problem was fixed, and so should be
   unaffected. See the
   [0.33.5 release notes (0.33.5-from-0.33.4.md)](https://github.com/bup/bup/blob/main/note/0.33.5-from-0.33.4.md)
   for additional information.

"Incidental" repairs may also be performed --- repairs that do not
functionally alter the result. For example, bup records symlink
targets in two places, but generally only refers to one of them. If
the other one is missing, it can and will be restored from the first.

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

    # Resplit (rewrite) the archives branch. Note that, done all at
    # once, this may require additional space up to the size of the
    # archives branch. The pick methods can do the rewriting more
    # selectively or incrementally. (Assume BUP_DIR has no split
    # settings.)
    #
    $ git --git-dir "$BUP_DIR" config bup.split.trees true
    $ git --git-dir "$BUP_DIR" config bup.split.files legacy:16
    $ bup get --rewrite --append: archives archives-resplit
    #
    # Check that archives-resplit looks OK, perhaps via trial
    # restores, joining it, etc. (see CAUTION above), and once
    # satisfied, perhaps...
    #
    $ bup rm archives
    $ bup gc
    $ git --git-dir "$BUP_DIR" branch -m archives-resplit archives
    #
    # Repair a single save.
    $ bup get --repair --pick archives/latest fixed
    #
    # Check that fixed/latest looks OK, perhaps via trial
    # restores, joining it, etc. (see CAUTION above).


# EXIT STATUS

An exit status of 3 indicates that repairs were needed and were
successful, and that no other errors occurred.

# SEE ALSO

`bup-on`(1), `bup-tag`(1), `ssh_config`(5)

# BUP

Part of the `bup`(1) suite.
