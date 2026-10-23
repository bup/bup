Notable changes in main (incomplete)
====================================

May require attention
---------------------

* Previously, `bup get` incorrectly handled invocations that requested
  a transfer that depended on a git reference (branch or tag) that was
  modified by an earlier transfer.  For example, it could omit
  intermediate items from the result when asked to do this:

      bup get -s SRC ... --pick x/SAVE-1 --pick x/SAVE-2 --pick x/SAVE-3

  It would omit SAVE-2 from the updated x branch, though the content
  would still be in the repository (barring a subsequent `gc`).

  This should now be fixed, and so the command above will produce an x
  branch with SAVE-2 preceding SAVE-3, and SAVE-1 preceding SAVE-2,
  as intended.

  This was the result of an undocumented attempt to defer all
  reference updates until after all of the transfers.  The updates now
  happen immediately after each individual transfer.

  bup should be upgraded on both the client and server (when
  relevant).

* `bup prune-older` did not correctly consider the year when pruning
  dailies or monthlies and adjacent saves had the same day or month
  but different years.  It would incorrectly prune all but the most
  recent save in a contiguous group.  For example if you had only
  these saves:

      2021-01-01-...
      2022-01-01-...
      2023-01-01-...
      2024-01-02-...
      2025-01-01-...

  then pruning with `--keep-dailies-for forever` would drop 2022 and
  2023, leaving you with:

      2021-01-01-...
      2024-01-02-...
      2025-01-01-...

  when it should have kept them all.

General
-------

* `bup get --repair --pick ...` and `--append` can now repair saves
  with a missing root tree or root metadata (e.g. missing git level
  `some/SAVE/.bupm` file).  For now, when the entire root tree is
  missing it is replaced with an empty directory, and a missing .bupm
  is treated the same as an "abridged" .bupm (see `bup-get(1)` for
  more information).  Previously the repair would just fail.

Bugs
----

* `bup tag` now reports invalid tag names as a usage error rather than
  throwing an exception.

* `bup ls` now exits with status 2 for access failures, rather than 1;
  this was overlooked in the general shift from 1 to 2 for errors in
  0.34 (see the 0.34 release notes).

Thanks to (at least)
====================

...
