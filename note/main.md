Notable changes in main (incomplete)
====================================

Bugs
----

* `bup get --repair --pick ...` can now repair saves with a missing
  root tree or `some/SAVE/.bupm` file.  Currently, in both cases, it
  replaces the root tree with an empty directory. Previously it would
  crash.  Eventually we'd like to have it drop only the `.bupm` file
  (the metadata) when it's missing rather than the entire tree.

Thanks to (at least)
====================

...
