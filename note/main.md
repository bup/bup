Notable changes in main (incomplete)
====================================

May require attention
---------------------

* The build system (e.g. `./configure`) no longer tries to find a
  suitable make, and we no longer try to redirect a non-GNU make to
  GNU make.  Whatever make you invoke must be GNU make >= 3.81.  On
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

Thanks to (at least)
====================

...
