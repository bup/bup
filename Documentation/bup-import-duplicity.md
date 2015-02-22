% bup-import-duplicity(1) Bup %BUP_VERSION%
% Zoran Zaric <zz@zoranzaric.de>, Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-import-duplicity - import duplicity backups

# SYNOPSIS

bup import-duplicity [-n] \<source-url\> \<save-name\>

# DESCRIPTION

`bup import-duplicity` imports all of the duplicity backups at
`source-url` into `bup` via `bup save -n save-name`.  The bup saves
will have the same timestamps (via `bup save --date`) as the original
backups.

Because this command operates by restoring each duplicity backup to a
temporary directory, the extent to which the metadata is preserved
will depend on the characteristics of the underlying filesystem,
whether or not you run `import-duplicity` as root (or under
`fakeroot`(1)), etc.

Note that this command will use [`mkdtemp`][mkdtemp] to create
temporary directories, which means that it should respect any
`TEMPDIR`, `TEMP`, or `TMP` environment variable settings.  Make sure
that the relevant filesystem has enough space for the largest
duplicity backup being imported.

Since all invocations of duplicity use a temporary `--archive-dir`,
`import-duplicity` should not affect ~/.cache/duplicity.

# OPTIONS

-n,--dry-run
:   don't do anything; just print out what would be done

# EXAMPLES

    $ bup import-duplicity file:///duplicity/src/ legacy-duplicity

# BUP

Part of the `bup`(1) suite.

[mkdtemp]: https://docs.python.org/2/library/tempfile.html#tempfile.mkdtemp
