---
title: How bup (before 0.33.5) might create incomplete trees
---

Versions of bup before 0.33.5 had three issues that could cause a
repository to end up with trees that had dangling references,
i.e. missing files, parts of files, subtrees, etc.  This document
describes those issues in greater detail.

## Background: git storage model

In git, we have the following structure for an individual commit with
directories and files, labeled as "name (git-type hash)":

<center>![](missing-objects-fig-git-model.svg)</center>

bup extends this model such that large files may be split into their
own subtrees during deduplication:

<center>![](missing-objects-fig-bup-model.svg)</center>

Files can also be split into multiple levels:

<center>![](missing-objects-fig-bup-model-2.svg)</center>

There are some more details, but the git model holds overall.  Commits
refer to their parent commits and a single tree, and trees refer to
their children (blobs and trees) -- and of course each object is
identified by its content hash.

> Note: For the sake of simplicity I'm drawing everything as trees in
> this document. In reality, the bup deduplication works exactly
> because it is _not_ a tree, but rather a directed acyclic graph
> (DAG). Multiple backup commits that record unchanged or otherwise
> identical directories or files obviously point to the object(s)
> representing those, shared across them.

## How `bup save` operates

When reading files and directories from the filesystem, `bup save`
will create a number of blob and tree objects, store them into the
repository if not already present, and (usually) finally create a new
commit object that points to the previous commit object and the new
root tree object.

Each "plain" file saved into the repository is uniquely identified by
the hash (SHA-1) of its object.  As mentioned above, and unlike git, a
file might be stored as a tree.

After reading a file or directory, `bup save` also updates the bup
`index` (not to be confused with git packfile indexes) entry for it
with the related hash. This helps speed up the next `bup save` run --
if the file is unchanged during the next `bup index` run, the next
`bup save` can simply check whether the object with the hash recorded
in the index is present in the repository, and doesn't have to
open/read the file or directory again if so.

## How `bup get` operates

Conceptually, `bup get` simply walks over the graph of a set of objects
in the source repository, checks if the object is present in the
destination repository, and if not then it copies the object over.
If it encounters a tree object that is already present in the destination
repository, it does _not_ walk into that object, for performance
reasons.

## How `bup prune-older`/`bup rm` operate

Again conceptually, this works by cutting pieces out of the chain of
commits, for example a `bup rm saves/2024-10...` will change
this branch:

<center>![](missing-objects-fig-rm-before.svg)</center>

into this:

<center>![](missing-objects-fig-rm-after.svg)</center>

As you can see, the save (commit) `2024-10...` object and the
trees/blobs it points to still exist in the repository, though they're
detached from `saves`.

## How `bup gc` operates

GC is intended to clean up those dangling objects. So after the prune example
above, ideally we want to have in the repository only this left after GC:

<center>![](missing-objects-fig-rm-after-gc.svg)</center>

This is not exactly what happens, unfortunately. We're still doing some
background, so more on this later.

## Object existence checking

In order to check if objects already exist in the repository, bup uses
three different data structures:

### `*.idx` files

For each pack file, git and bup use an idx file that contains a list of all
the objects in the pack file, and also points to the object inside the
pack, so you can retrieve a desired object. Checking for existence just
requires seeing if the object name is in the list.

These files can be recreated from the pack files, but this is expensive.

### `*.midx` files

The midx files have a similar structure, except they cover multiple pack
files and tell you which pack file an object is located in (but not
where in that pack file).

These files are created from the `*.idx` files and are ephemeral, they can
be destroyed and recreated at will.

### Bloom filter

To see if it's even worth checking, bup uses a [Bloom
filter](https://en.wikipedia.org/wiki/Bloom_filter) (`bup.bloom`),
which is a probabilistic data structure that can say "I've never heard
about this object before" and "I might have seen this object
before". If it says the object doesn't exist, there's no need to check
the midx/idx files. If it says the object _might_ exist, then those
files need to be consulted. The Bloom filter is therefore not relevant
to the issues at hand.

Just like the `*.midx` files, this file is created from the `*.idx`
files (or perhaps from the `*.midx` that in turn come from `*.idx`)
and is also ephemeral, so it can be destroyed and recreated at will.

## Remote save - `bup save -r`

In order to avoid transferring a lot of data that might not be needed,
bup clients synchronize the idx files with the idx files on the server
when connecting. They then rebuild midx/bloom files, and then the save
can do a local "does this object exist already" check, rather than either
shipping the object to the server for it to check, or asking the server
to check, both of which would take a lot of time (due to bandwidth and
latency respectively.)

## Bug #1 (remotely cached midx files)

When GC is done on a repository, of course some pack files will be
removed along with their idx files.

When a client synchronizes the idx files, it deletes the idx files
from the cache that were removed on the server repository, so that
testing for objects that were previously contained in them should no
longer indicate that they already exist.

However, the midx files are incorrectly updated. Remember that
midx files are created from the idx files. When updating the midx
files after the idx synchronization, bup doesn't check whether or
not any of the midx file(s) still contain(s) content from a now-deleted
idx file. This can lead to checking for object existence and being
given the answer that an object exists, even though it was GC'ed in
the repository, and in fact the idx files no longer show that it
exists, only the incorrect midx does.

This in turn can lead to `save -r` or `get -r` omitting an object that had
previously existed, but has been removed by GC on the remote (omitted
because the midx still thinks the remote has it).

This doesn't happen with local use of the repository (without `-r` or
`bup on`) since gc removes all midx/bloom files.

Since version 0.33.5, `bup` regenerates the midx files correctly.

## Bug #2

I previously showed that after prune, you have this set of objects
in the repository:

<center>![](missing-objects-fig-rm-after.svg)</center>

Remember that after GC, we want this set of objects:

<center>![](missing-objects-fig-rm-after-gc.svg)</center>

Unfortunately, the current GC fundamentally doesn't work that way (and
that's the issue), and it might only remove the `2024-11... (c1...)`
and `2024-10...` commits and `hosts (blob 76...)`, leaving us with:

<center>![](missing-objects-fig-gc-dangling.svg)</center>

See ["How gc (before 0.33.5) can create dangling references"](#how-gc-before-0.33.5-can-create-dangling-references)
below for further details regarding the cause.

### Effect on `bup get`

If you run `bup get` now to write to this repository, and it
encounters the `etc/` tree, originally from `save 2`, in the set of
objects to transfer, it will see that it already exists (because it
*is* still in the repository's packfiles), and as explained earlier,
will assume it's complete and re-use it, without delving further. This
will leave the repository broken, because now, whatever `get` is
building will have a reference to the `etc/` tree that itself refers
to the missing `hosts` blob.

### Effect on `bup save`

Similarly, if `bup save` encounters the `etc/` tree, originally from
`save 2`, in the `index`, and sees that it already exists in the
repository, it will prune its index traversal at that point, and
re-use the existing, broken `etc/ (tree ee)` object without noticing
that the tree is broken.

This can (also) happen if a save is aborted in the middle, `gc` is run
to clean up the repo and remove unreferenced objects, and some objects
that are referenced by the index (say the `etc/` tree) are not removed
by the `gc`, while some other objects (say `hosts`) that are referred
to by the preserved objects are themselves removed.

However, if the index doesn't exist (say due to a `bup index
--clear`), then it shouldn't be possible for `bup save` to create the
problem, because when saving a path it creates all the objects the
path is comprised of, from the bottom (leaves) up, and then checks to
see if the object exists in the repository. This process would
encounter `hosts` first, and store it, fixing the broken `etc/` tree
before it's reached.

### How gc (before 0.33.5) can create dangling references

There are actually two reasons it can do this.

#### Probabilistic liveness detection

The first reason is that the garbage collection before 0.33.5 tracks
tree and commit objects probabilistically, not precisely. It
determines whether they're live via a Bloom filter populated by a
reachability walk through all refs.  (As of 0.33.5 trees and commits
are tracked precisely.)

Because [Bloom filters](https://en.wikipedia.org/wiki/Bloom_filter)
can only say "definitely not present" and "maybe present", it means
that some other random object can cause `/etc (tree ee...)` to be
considered "maybe present" (live) when it isn't actually reachable
(wasn't traversed during the walk).

First, the Bloom filter is populated with live objects.  Each live
object sets N bits in the Bloom filter (just 2 here):

<center>![](missing-objects-fig-bloom-set.svg)</center>

Then the liveness check can erroneously return true if say `etc/ (tree
ee...)` happens to map to N bits that have been set by other objects:

<center>![](missing-objects-fig-bloom-get.svg)</center>

#### Pack file rewrite threshold

It's also possible that `etc/ (tree ee...)` and `hosts (blob 76...)`
end up in separate pack files (depending on how/when they were
written), and the pack file containing `hosts` ends up being
rewritten, dropping `hosts` (because it has more dead objects than the
threshold), but the pack file containing `etc/ (tree ee)` does not
(because it had enough live objects to survive intact).

## Bug #3 (bup get)

While working on all of this, we noticed that `bup get` can also leave
the repository with incomplete trees if it is aborted at the wrong
time during a transfer.  Imagine we have a save like this:

<center>![](missing-objects-fig-get-bug-save.svg)</center>

Say that `bup get` is called to transfer `c-1` from another
repository.  For simplicity we'll ignore its parent commit.  It should
transfer `c-1`, `/`, `etc`, `fstab`, and `hosts`.  Unfortunately,
versions of `bup get` before 0.33.5 will transfer the objects in
precisely that order, which means that if `bup get` is interrupted at
the wrong time, say just after fetching `fstab`, it will leave an
incomplete `etc/` tree in the destination repo (because the `hosts`
blob is missing).  Any future `bup get` attempts won't fix the problem
because (as described previously) they will see `etc` in the
destination repository and assume it's complete.

And of course there are many ways `bup get` might be interrupted: full
filesystem, system shutdown, network issues, or perhaps even more
likely, `^C` (SIGINT).

> Note: If you were to run `bup gc` after the aborted transfer even
> the broken version of it would clean up the freshly written pack
> file since the objects aren't connected yet, but chances are that
> one would just attempt to resume the transfer, resulting in it being
> connected, but potentially incomplete. Also, due to the Bloom
> collision bug, gc might incorrectly keep some objects.
