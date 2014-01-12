% bup-split(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-split - save individual files to bup backup sets

# SYNOPSIS

bup split \[-t\] \[-c\] \[-n *name*\] COMMON\_OPTIONS

bup split -b COMMON\_OPTIONS

bup split \<--noop \[--copy\]|--copy\> COMMON\_OPTIONS

COMMON\_OPTIONS
  ~ \[-r *host*:*path*\] \[-v\] \[-q\] \[-d *seconds-since-epoch*\] \[\--bench\]
    \[\--max-pack-size=*bytes*\] \[-#\] \[\--bwlimit=*bytes*\]
    \[\--max-pack-objects=*n*\] \[\--fanout=*count*\]
    \[\--keep-boundaries\] \[--git-ids | filenames...\]

# DESCRIPTION

`bup split` concatenates the contents of the given files
(or if no filenames are given, reads from stdin), splits
the content into chunks of around 8k using a rolling
checksum algorithm, and saves the chunks into a bup
repository.  Chunks which have previously been stored are
not stored again (ie. they are 'deduplicated').

Because of the way the rolling checksum works, chunks
tend to be very stable across changes to a given file,
including adding, deleting, and changing bytes.

For example, if you use `bup split` to back up an XML dump
of a database, and the XML file changes slightly from one
run to the next, nearly all the data will still be
deduplicated and the size of each backup after the first
will typically be quite small.

Another technique is to pipe the output of the `tar`(1) or
`cpio`(1) programs to `bup split`.  When individual files
in the tarball change slightly or are added or removed, bup
still processes the remainder of the tarball efficiently. 
(Note that `bup save` is usually a more efficient way to
accomplish this, however.)

To get the data back, use `bup-join`(1).

# MODES

These options select the primary behavior of the command, with -n
being the most likely choice.

-n, \--name=*name*
:   after creating the dataset, create a git branch
    named *name* so that it can be accessed using
    that name.  If *name* already exists, the new dataset
    will be considered a descendant of the old *name*.
    (Thus, you can continually create new datasets with
    the same name, and later view the history of that
    dataset to see how it has changed over time.)

-t, \--tree
:   output the git tree id of the resulting dataset.

-c, \--commit
:   output the git commit id of the resulting dataset.

-b, \--blobs
:   output a series of git blob ids that correspond to the chunks in
    the dataset.  Incompatible with -n, -t, and -c.

\--noop
:   read the data and split it into blocks based on the "bupsplit"
    rolling checksum algorithm, but don't do anything with the blocks.
    This is mostly useful for benchmarking.  Incompatible with -n, -t,
    -c, and -b.

\--copy
:   like `--noop`, but also write the data to stdout.  This can be
    useful for benchmarking the speed of read+bupsplit+write for large
    amounts of data.  Incompatible with -n, -t, -c, and -b.

# OPTIONS

-r, \--remote=*host*:*path*
:   save the backup set to the given remote server.  If *path* is
    omitted, uses the default path on the remote server (you still
    need to include the ':').  The connection to the remote server is
    made with SSH.  If you'd like to specify which port, user or
    private key to use for the SSH connection, we recommend you use
    the `~/.ssh/config` file.  Even though the destination is remote,
    a local bup repository is still required.

-d, \--date=*seconds-since-epoch*
:   specify the date inscribed in the commit (seconds since 1970-01-01).

-q, \--quiet
:   disable progress messages.

-v, \--verbose
:   increase verbosity (can be used more than once).

\--git-ids
:   stdin is a list of git object ids instead of raw data.
    `bup split` will read the contents of each named git
    object (if it exists in the bup repository) and split
    it.  This might be useful for converting a git
    repository with large binary files to use bup-style
    hashsplitting instead.  This option is probably most
    useful when combined with `--keep-boundaries`.

\--keep-boundaries
:   if multiple filenames are given on the command line,
    they are normally concatenated together as if the
    content all came from a single file.  That is, the
    set of blobs/trees produced is identical to what it
    would have been if there had been a single input file. 
    However, if you use `--keep-boundaries`, each file is
    split separately.  You still only get a single tree or
    commit or series of blobs, but each blob comes from
    only one of the files; the end of one of the input
    files always ends a blob.

\--bench
:   print benchmark timings to stderr.

\--max-pack-size=*bytes*
:   never create git packfiles larger than the given number
    of bytes.  Default is 1 billion bytes.  Usually there
    is no reason to change this.

\--max-pack-objects=*numobjs*
:   never create git packfiles with more than the given
    number of objects.  Default is 200 thousand objects. 
    Usually there is no reason to change this.
    
\--fanout=*numobjs*
:   when splitting very large files, try and keep the number
    of elements in trees to an average of *numobjs*.

\--bwlimit=*bytes/sec*
:   don't transmit more than *bytes/sec* bytes per second
    to the server.  This is good for making your backups
    not suck up all your network bandwidth.  Use a suffix
    like k, M, or G to specify multiples of 1024,
    1024*1024, 1024*1024*1024 respectively.

-*#*, \--compress=*#*
:   set the compression level to # (a value from 0-9, where
    9 is the highest and 0 is no compression).  The default
    is 1 (fast, loose compression)


# EXAMPLE
    
    $ tar -cf - /etc | bup split -r myserver: -n mybackup-tar
    tar: Removing leading /' from member names
    Indexing objects: 100% (196/196), done.
    
    $ bup join -r myserver: mybackup-tar | tar -tf - | wc -l
    1961
    

# SEE ALSO

`bup-join`(1), `bup-index`(1), `bup-save`(1), `bup-on`(1), `ssh_config`(5)

# BUP

Part of the `bup`(1) suite.
