Notable changes in main (incomplete)
====================================

May require attention
---------------------

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

* A `pack.packSizeLimit` set in the destination repository will now
  take precedence over any value set in the local repository when both
  are involved.  Previously the destination repository's value was
  ignored.

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

* The deduplication granularity can now be changed by a new
  `bup.split.files` configuration option which defaults to `legacy:13`
  (the current behavior), but should probably be set to a higher value
  like `legacy:16` in new repositories (say via `git-config --file
  REPO/config bup.split.files legacy:16`).
  The default for new repositories will eventually be raised. See
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

Bugs
----

* A bug has been fixed that could cause any internal subcommand
  (e.g. not `import-rsnapshot`) to hang when running interactively
  (i.e. with a controlling terminal).

* Saves with identical dates won't end up with the same name
  (e.g. 2025-01-08-135615 in "bup ls BRANCH") when they're not
  adjacent -- when one isn't the other's direct parent. Previously bup
  appended an increasing "-N" to disambiguate duplicates, but only
  when they were directly related. Now it appends across all
  duplicates.

* When run on an existing repository, `bup init` will now leave
  changes to `core.logAllRefUpdates` alone.

Build system
------------

`./configure` now depends on a bash with support for associative
arrays.  Accordingly, `prep-for-macos-build` has been adjusted to
install bash via `brew`.

Thanks to (at least)
====================

...
