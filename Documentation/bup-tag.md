% bup-tag(1) Bup %BUP_VERSION%
% Gabriel Filion <lelutin@gmail.com>
% %BUP_DATE%

# NAME

bup-tag - tag a commit in the bup repository

# SYNOPSIS

bup tag

bup tag \<tag name\> \<committish\>

bup tag -d \<tag name\>

# DESCRIPTION

`bup tag` lists, creates or deletes a tag in the bup repository.

A tag is an easy way to retrieve a specific commit. It can be used to mark a
specific backup for easier retrieval later.

When called without any arguments, the command lists all tags that can
be found in the repository. When called with a tag name and a commit ID
or ref name, it creates a new tag with the given name, if it doesn't
already exist, that points to the commit given in the second argument. When
called with '-d' and a tag name, it removes the given tag, if it exists.

bup exposes the contents of backups with current tags, via any command that
lists or shows backups. They can be found under the /.tag directory.  For
example, the 'ftp' command will show the tag named 'tag1' under /.tag/tag1.

Tags are also exposed under the branches from which they can be reached. For
example, if you create a tag named 'important' under branch 'computerX', you
will also be able to retrieve the contents of the backup that was tagged under
/computerX/important. This is done as a convenience, and should the branch
'computerX' be deleted, the contents of the tagged backup will be available
through /.tag/important as long as the tag is not deleted.

# OPTIONS

-d, \--delete
:   delete a tag

# EXAMPLE
    
    $ bup tag new-puppet-version hostx-backup
    
    $ bup tag
    new-puppet-version
    
    $ bup ftp "ls /.tag/new-puppet-version"
    files..

    $ bup tag -d new-puppet-version

# SEE ALSO

`bup-save`(1), `bup-split`(1), `bup-ftp`(1), `bup-fuse`(1), `bup-web`(1)

# BUP

Part of the `bup`(1) suite.
