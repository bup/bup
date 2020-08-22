
Notable changes in 0.31 (since 0.30.1)
======================================

* Python 3 is now supported, and Python 2 support is deprecated.  It's
  possible that we'll stop new development for Python 2 fairly soon.
  If so, we'll probably continue to fix bugs in the last Python 2
  compatible version for a while, but please make plans to migrate.

* `bup features` has been added.  It reports information about bup
  itself, including the Python version, and the current availability
  of features like readline or support for POSIX ACLs.

May require attention
---------------------

* bup now relies on libacl directly instead of python-pylibacl, which
  will require installing the relevant packages (e.g. libacl1-dev)
  before building.

* bup now relies on libreadline directly instead of python's built-in
  support, which will require installing the relevant packages
  (e.g. libreadline-dev) before building.

* `bup version --tag` has been removed.  It was actually a synonym for
  `bup version`, which still works fine.  The fact that the version
  may have a corresponding git tag is no longer relevant to the
  command.

* `git describe` style strings will no longer appear in the `bup
  version` for non-release builds.  The version in that case will
  currently just be formatted as `PENDING_RELEASE~HASH`, where `~` has
  the [Debian semantics](https://www.debian.org/doc/debian-policy/ch-controlfields.html#version),
  for example, 0.31~5ac3821c0f1fbd6a1b1742e91ffd556cd1116041).  This
  is part of the fix for the issue with varying `git archive` content
  mentioned below.

General
-------

* `bup fsck` should now avoid displaying `par2` errors when testing it
  for parallel processing support.

* The documentation for the hashsplit algorithm in DESIGN has been
  updated to reflect quirks of the implementation, which didn't quite
  match the original specification.

Bugs
----

* When running `bup on` with a remote ssh `ForceCommand`, bup should
  now respect that setting when running sub-commands.

* It should no longer be possible for the content of archives generated
  by `git archive` (including releases retrieved from github) to vary
  based on the current set of repository refs (tags, branches, etc.).
  Previously archives generated from the same tag could differ
  slightly in content.

Build and install
-----------------

* `bup` itself is now located in now located in the cmd/ directory in
  the install tree and finds sub-commands, etc. relative to its own
  location.

* The metadata tests should no longer fail on systems with SELinux
  enabled.

Thanks to (at least)
====================

Aaron M. Ucko, Aidan Hobson Sayers, Alexander Barton, Brian Minton,
Christian Cornelssen, Eric Waguespack, Gernot Schulz, Greg Troxel,
Hartmut Krafft, Johannes Berg, Luca Carlon, Mark J Hewitt, Ralf
Hemmecke, Reinier Maas, Rob Browning, Robert Edmonds, Wyatt Alt, Zev
Eisenberg, gkonstandinos, and kd7spq
