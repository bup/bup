% bup-cat-file(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-cat-file - extract archive content (low-level)

# SYNOPSIS

bup cat-file [--meta|--bupm] <*path*>

# DESCRIPTION

`bup cat-file` extracts content associated with *path* from the
archive and dumps it to standard output.  If nothing special is
requested, the actual data contained by *path* (which must be a
regular file) will be dumped.

# OPTIONS

\--meta
:   retrieve the metadata entry associated with *path*.  Note that
    currently this does not return the raw bytes for the entry
    recorded in the relevant .bupm in the archive, but rather a
    decoded and then re-encoded version.  When that matters, it should
    be possible (though awkward) to use `--bupm` on the parent
    directory and then find the relevant entry in the output.

\--bupm
:   retrieve the .bupm file associated with *path*, which must be a
    directory.

# EXAMPLES

    # Retrieve the content of somefile.
    $ bup cat-file /foo/latest/somefile > somefile-content

    # Examine the metadata associated with something.
    $ bup cat-file --meta /foo/latest/something | bup meta -tvvf -

    # Examine the metadata for somedir, including the items it contains.
    $ bup cat-file --bupm /foo/latest/somedir | bup meta -tvvf -

# SEE ALSO

`bup-join`(1), `bup-meta`(1)

# BUP

Part of the `bup`(1) suite.
