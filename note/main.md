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

General
-------

* `bup init DIRECTORY` is now supported, and places the repository in
  the given `DIRECTORY` which takes precedence over `-d` and
  `BUP_DIR`.

* `bup web` has been improved.  It should better preserve page
  settings while navigating, and has added settings to toggle the
  display of various types of information, including path sizes,
  hashes, and metadata.  Symlinks targets are now shown, and the
  layout, in general, has been changed (including trivial support for
  dark mode).

Bugs
----

* A bug has been fixed that could cause any internal subcommand
  (e.g. not `import-rsnapshot`) to hang when running interactively
  (i.e. with a controlling terminal).

Thanks to (at least)
====================

...
