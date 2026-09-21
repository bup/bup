Notable changes in main (incomplete)
====================================

May require attention
---------------------

* Previously, `bup get` could omit intermediate items from the result
  when asked to update a ref (branch or tag) more than once in a
  single invocation.  For example

      bup get -s SRC ... --pick x/SAVE-1 --pick x/SAVE-2 x/SAVE-3

  would omit SAVE-2 from the updated x branch, though the content
  would still be in the repository (barring a subsequent `gc`).

  This should be fixed, and the command above will produce an x branch
  with SAVE-2 preceeding SAVE-3, and SAVE-1 preceeding SAVE-2, as
  intended.

Bugs
----

* `bup get --repair --pick ...` and `--append` can now repair saves
  with a missing root tree or `some/SAVE/.bupm` file.  Currently, in
  both cases, it replaces the root tree with an empty directory.
  Previously it would crash.  Eventually we'd like to have it drop
  only the `.bupm` file (the metadata) when it's missing rather than
  the entire tree.

* `bup get` now validates repeated ref (branch or tag) updates more
  correctly.  Previously when multiple targets were specified, it
  wouldn't properly account for the actions of preceeding METHODs
  (`--pick`, `--replace`, etc.) when evaluating the correctness of a
  command before execution.

Thanks to (at least)
====================

...
