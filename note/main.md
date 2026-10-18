Notable changes in main (incomplete)
====================================

May require attention
---------------------

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

Bugs
----

* `bup tag` now reports invalid tag names as a usage error rather than
  throwing an exception.

Thanks to (at least)
====================

...
