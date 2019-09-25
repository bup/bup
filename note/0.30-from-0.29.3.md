
Notable changes in 0.30 as compared to 0.29.3
=============================================

May require attention
---------------------

* The minimum `git` version required is now 1.5.6.

* The `prune-older` command now keeps the most recent save in each
  period group (day, week, month, ...) rather than the oldest.

* `bup` now adds a zero-padded suffix to the names of saves with the
  same timestamp (e.g. 1970-01-01-214640-07) in order to avoid
  duplicates.  The sequence number currently represents the save's
  reversed position in default `git rev-list` order, so that given:
    
      /foo/1970-01-01-214640-09
      /foo/1970-01-01-214640-10
    
  In the normal case, the -10 save would be the next save made after
  -09 (and the -09 save would be the single parent commit for -10).

* `bup` is not currently compatible with Python 3 and will now refuse
  to run if the Python version is not 2 unless
  `BUP_ALLOW_UNEXPECTED_PYTHON_VERSION=true` is set in the environment
  (which can be useful for development and testing).

* `bup ls -s` now reports the tree hash for commits unless
  `--commit-hash` is also specified.

General
-------

* `bup get` has been added.  This command allows the transfer or
  rewriting of data within and between repositories, local or remote.
  Among other things, it can be used to append remote saves to a local
  branch, which by extension supports merging repositories.  See
  `bup-get(1)` for further information, and please note, this is a new
  *EXPERIMENTAL* command that can (intentionally) modify your data in
  destructive ways.  It is potentially much more dangerous than most
  `bup` commands.  Treat with caution.

* `bup` can now restore directly from a remote repository via `bup
  restore -r host:path ...`.  See `bup-restore(1)` for more
  information.

* `bup ls` can now report information for remote repositories via `bup
  ls -r host:path ...`.  See `bup-ls(1)` for more information.

* `bup` should respect the git pack.packSizeLimit setting when writing
  packfiles, though at the moment it will only affect a remote
  repository when the option is set there directly.

* `bup save` now stores the size for all links and normal files.  For
  directories saved using this new format retrieving file sizes for
  larger files should be notably less expensive.  Among other things
  this may improve the performance of commands like `bup ls -l` or
  `find /some/fuse/dir -ls`.

* The VFS (Virtual File System) that underlies many operations, and
  provides the basis for commands like `restore`, `ls`, etc. has been
  rewritten in a way that makes remote repository access easier,
  should decrease the memory footprint in some cases (e.g. for bup
  fuse), and should make it easier to provide more selective caching.
  At the moment, data is just evicted at random once a threshold is
  reached.

* A `--noop <--blobs|--tree>` option has been added to `bup split`
  which prints the resulting id without storing the data in the
  repository.

Bugs
----

* The way `bup` handles output from subprocesses (diagnostics,
  progress, etc.) has been adjusted in a way that should make it less
  likely that bup might continue running after the main process has
  exited, say via a C-c (SIGINT).

* `bup` should now respect the specified compression level when
  writing to a remote repository.

* `bup restore` now creates FIFOs with mkfifo, not mknod, which is
  more portable.  The previous approach did not work correctly on (at
  least) some versions of NetBSD.

* `bup` should no longer just crash when it encounters a commit with a
  "mergetag" header.  For the moment, it just ignores them, and
  they'll be discarded whenever `bup` rewrites a commit, say via the
  `rm`, `prune-older`, or `get` commands.

* The bloom command should now end progress messages with \r, not \n,
  which avoids leaving spurious output lines behind at exit.

* A missing space has been added to the `bup split --bench` output.

* Various Python version compatibility problems have been fixed,
  including some of the incompatibilities introduced by Python 3.

* Some issues with mincore on WSL have been fixed.

* Some Android build incompatibilities have been fixed.


Build system
------------

* The tests no longer assume pwd is in /bin.

* The tests should be less sensitive to the locale.

* `test-meta` should no longer try to apply chattr +T to files.  'T'
  only works for directories, and newer Linux kernels actually reject
  the attempt (as of at least 4.12, and maybe 4.10).

* `test-rm` should no longer fail when newer versions of git
  automatically create packed-refs.

* `test-sparse-files` should be less likely to fail when run inside a
  container.

* `test-index-check-device` and `test-xdev` now use separate files for
  their loopback mounts.  Previously each was mounting the same image
  twice, which could produce the same device number.

Thanks to (at least)
====================

Alexander Barton, Artem Leshchev, Ben Kelly, Fabian 'xx4h' Melters,
Greg Troxel, Jamie Wyrick, Julien Goodwin, Mateusz Konieczny,
Nathaniel Filardo, Patrick Rouleau, Paul Kronenwetter, Rob Browning,
Robert Evans, Tim Riemenschneider, and bedhanger
