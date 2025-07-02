Notable changes in main (incomplete)
====================================

May require attention
---------------------

* Previously, `bup get --force-pick: SRC /.tag/DEST` created broken
  commits if the `DEST` was not itself a commit (the parent would be
  whatever `DEST` initially pointed to).

* `bup` now prefers the XDG cache location (typically
  `~/.cache/bup/remote/`) for the client index cache, but existing
  `$BUP_DIR/index-cache` directories will take precedence.  See
  `bup-config`(5) for additional information.

* `bup` will now correctly disambiguate save names on a given branch
  that have the same timestamp (committer time), even when the saves
  are not adjacent. `bup` disambiguates duplicates by adding a unique
  trailing integer, e.g. `archive/2025-03-29-124014-1`,
  `archive/2025-03-29-124014-2`, and previously, it wouldn't notice
  the duplication unless one save was the parent of the other. That's
  typically the case unless the system clock has been changed, or
  commands like `bup get --pick` have been used.

* The build system (e.g. `./configure`) no longer tries to find a
  suitable make, and we no longer try to redirect a non-GNU make to
  GNU make.  Whatever make you invoke must be GNU make >= 4.2.  On
  many systems that will be `make` or `gmake`.

* `bup fsck --repair` promises to exit with a status of 1 whenever
  repairs are needed and successful, and no other errors occur.

* `bup fsck --quick` now checks the packfile indexes too.  Previously
  it only checked the packfiles.

* `bup fsck --generate` and `--repair` now exit immediately with an
  error when a suitable par2 isn't available.  Previously `--generate`
  would just print "skipped".

* `bup fsck` now only accepts `*.pack` arguments, and it no longer
  generates recovery information for the `*.idx` files so that all of
  the recovery blocks will protect the packfile.  This is safer given
  that the `.idx` files can be (and now are) trivially regenerated
  from the packfiles during `--repair` when needed.

* Some prior exit statuses of 1 have been changed to a different
  non-zero value.  `bup` is migrating away from exiting with status 1
  for anything other than "false".  This is used by commands like
  `verify-ref-links` that need to report a true or false result like
  `grep` does.

* `bup` now only considers the repository's `config` settings.
  Previously configuration values would be determined by the default
  `git-config`(1) worktree/local/global/system hierarchy, meaning, for
  example, that the host's (local or remote) `~/.gitconfig` or
  `/etc/gitconfig` would also be consulted.  The only existing
  affected value is `pack.packSizeLimit`.

* `bup` now only considers a `pack.packSizeLimit` set in the
  destination repository.

* `bup split --copy` now writes the split data to standard output
  instead of Python memoryview representations like

      <memory at 0x7f7a89358ac0><memory at 0x7f7a89358a00>...

General
-------

* Repositories should now have a unique `bup.repo.id` set in the
  config. `bup init` automatically adds one both during initial
  creation, or when run again on an existing repository. See
  `bup-config`(5) for more information.

* The REMOTE directory name in the client index cache (typically
  `~/.bup/index-cache/REMOTE`) is now the `bup.repo.id` when the
  remote repository provides, one and existing directories will be
  renamed when appropriate and possible.

* `bup init DIRECTORY` is now supported, and places the repository in
  the given `DIRECTORY` which takes precedence over `-d` and
  `BUP_DIR`.

* `bup init` now configures `init.defaultBranch` to avoid newer git
  versions describing ways to change the default branch.

* The deduplication granularity can now be changed by a new
  `bup.split.files` configuration option which defaults to `legacy:13`
  (the current behavior), but should probably be set to a higher value
  like `legacy:16` in new repositories (say via `git-config --file
  REPO/config bup.split.files legacy:16`).
  The default for new repositories will eventually be raised. See
  `bup-config`(5) for additional information.

* `bup` will split directories when `bup.split.trees` is `true`. This
  can notably decrease the size of new data added to the repository
  when large directories change (e.g. large active Maildirs). See
  `bup-config`(5) for additional information.

* The default pack compression level can now be configured via either
  `pack.compression` or `core.compression`.  See `bup-config`(5) for
  additional information.

* `bup web` has been improved.  It should better preserve page
  settings while navigating, and has added settings to toggle the
  display of various types of information, including path sizes,
  hashes, and metadata.  Symlinks targets are now shown, and the
  layout, in general, has been changed (including trivial support for
  dark mode).

* `bup` no longer tries to "filter" output when running
  interactively. Previously it would try to prevent or at least
  mitigate any intermingling of output (lines) from itself and
  children (e.g. par2, git, etc.), for example with respect to
  progress-style output relying on '\r' (carriage returns). The
  previous attempts have been complex and fragile and it's not clear
  they've been worth the cost. Our hope is to handle any issues that
  still arise in some simpler way.

* The server "mode" can now be set by a new
  `bup.server.deduplicate-writes` configuration option. See
  `bup-config(5)` for additional information.

* A local repository should no longer be required to run `bup index
  -f` or a remote `save`.

* `bup gc` should now avoid reading data that it doesn't actually
  need. Previously it would retrieve (and discard) a lot of unneeded
  blobs during a collection.

* When verbose (via `-v...`), `bup gc` and `bup validate-ref-links` no
  longer print paths while scanning the repository because earlier git
  (and then our use of git) didn't allow otherwise.

Bugs
----

* `bup on HOST get ...` should no longer hang in some situations where
  the client could provoke duplicate index-cache suggestions from the
  server, which the client then treated as an error.

* A bug has been fixed that could cause any internal subcommand
  (e.g. not `import-rsnapshot`) to hang when running interactively
  (i.e. with a controlling terminal).

* Saves with identical dates won't end up with the same name
  (e.g. 2025-01-08-135615 in "bup ls BRANCH") when they're not
  adjacent -- when one isn't the other's direct parent. Previously bup
  appended an increasing "-N" to disambiguate duplicates, but only
  when they were directly related. Now it appends across all
  duplicates.

* When run on an existing repository, `bup init` will no longer change
  existing `core.logAllRefUpdates` settings.

* `par2` changed its behavior in 1.0 to be incompatible with `bup`'s
  use of symlinks to mitigate a `par2` bug (see the [0.33.4 release
  notes](0.33.4-from-0.33.3.md) for additional information. `bup` now
  uses hardlinks instead.

Build system
------------

* `./configure` now depends on a bash with support for associative
  arrays.  Accordingly, `prep-for-macos-build` has been adjusted to
  install bash via `brew`.

Thanks to (at least)
====================

...
