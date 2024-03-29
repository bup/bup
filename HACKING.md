
Conventions?  Are you kidding?  OK fine.

Code Branching Model
====================

The main branch is the development branch, and stable releases are
tagged either from there, or from `VERSION.x` branches, created as
needed, for example `0.33.x`.

Any branch with a "tmp/" prefix might be rebased (often), so keep that
in mind when using or depending on one.

Any branch with a "tmp/review/" prefix corresponds to a patchset
submitted to the mailing list.  We try to maintain these branches to
make the review process easier for those not as familiar with patches
via email.


Current Trajectory
==================

Now that we've finished the 0.33 release, we're working on 0.34, and
although we're not certain which new features will be included, we're
considering:

  - Migrating hashsplitting to C.

  - Automatically splitting trees to avoid having to save large tree
    objects for large directories even if only a few files have
    changed or been added (e.g. maildirs).

  - Moving all of the compoents of the index to sqlite.  Right now the
    main index is an mmapped file, and the hard link and metadata
    databases are pickled.  As a result the index isn't transactional
    and suffers from bugs caused by "skew" across the components.

  - Better VFS performance for large repositories (i.e. fuse, ls,
    web...).

  - Better VFS caching.

  - Index improvements.

  - Incremental indexing via inotify.

  - Smarter (and quieter) handling of cross-filesystem metadata.

  - Encryption.

  - Support for alternate remote storage APIs.

If you have the time and inclination, please help review patches
posted to the list, or post your own.  (See "ways to help" below.)


More specific ways to help
==========================

Testing -- yes please.

With respect to patches, bup development is handled via the mailing
list, and all patches should be sent to the list for review (see
"Submitting Patches" below).

In most cases, we try to wait until we have at least one or two
"Reviewed-by:" replies to a patch posted to the list before
incorporating it into main, so reviews are an important way to help.
We also love a good "Tested-by:" -- the more the merrier.


Testing
=======

Individual tests can be run via

    ./pytest TEST

For example:

    ./pytest test/int/test_git.py
    ./pytest test/ext/test-ftp

If you have the xdist module installed, then you can specify its `-n`
option to run the tests in parallel (e.g. `./pytest -nauto ...`), or
you can specify `-j` to make, which will be translated to xdist with
`-j` becoming `-nauto` and `-jN` becoming `-nN`.

Internal tests that test bup's code directly are located in test/int,
and external tests that test bup from the outside, typically by
running the executable, are located in test/ext.

Currently, all pytests must be located in either test/ext or test/int.
Internal test filenames must match test_*.py, and external tests must
be located in text/ext and their filenames must match test-* (see
test/ext/conftest.py for the handling of the latter).  Any paths
matching those criteria will be automatically collected by pytest.

Some aspects of the environment are automatically restored after each
test via fixtures in conftest.py, including the state of the
environment variables and the working directory; the latter is reset
to the top of the source tree.

Submitting patches
==================

As mentioned, all patches should be posted to the mailing list for
review, and must be "signed off" by the author before official
inclusion (see ./SIGNED-OFF-BY).  You can create a "signed off" set of
patches in ./patches, ready for submission to the list, like this:

    git format-patch -s -o patches origin/main

which will include all of the patches since origin/main on your
current branch.  Then you can send them to the list like this:

    git send-email --to bup-list@googlegroups.com --compose patches/*

The use of --compose will cause git to ask you to edit a cover letter
that will be sent as the first message.

It's also possible to handle everything in one step:

    git send-email -s --to bup-list@googlegroups.com --compose origin/main

and you can add --annotate if you'd like to review or edit each patch
before it's sent.

For single patches, this might be easier:

    git send-email -s --to bup-list@googlegroups.com --annotate -n1 HEAD

which will send the top patch on the current branch, and will stop to
allow you to add comments.  You can add comments to the section with
the diffstat without affecting the commit message.

Of course, unless your machine is set up to handle outgoing mail
locally, you may need to configure git to be able to send mail.  See
git-send-email(1) for further details.

Oh, and we do have a ./CODINGSTYLE, hobgoblins and all, though don't
let that scare you off.  We're not all that fierce.


Even More Generally
===================

It's not like we have a lot of hard and fast rules, but some of the
ideas here aren't altogether terrible:

  http://www.kernel.org/doc/Documentation/SubmittingPatches

In particular, we've been paying at least some attention to the bits
regarding Acked-by:, Reported-by:, Tested-by: and Reviewed-by:.

<!--
Local Variables:
mode: markdown
End:
-->
