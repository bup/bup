bup: It backs things up
=======================

bup is a program that backs things up.  It's short for "backup." Can you
believe that nobody else has named an open source program "bup" after all
this time?  Me neither.

Despite its unassuming name, bup is pretty cool.  To give you an idea of
just how cool it is, I wrote you this poem:

                             Bup is teh awesome
                          What rhymes with awesome?
                            I guess maybe possum
                           But that's irrelevant.
			
Hmm.  Did that help?  Maybe prose is more useful after all.


Reasons bup is awesome
----------------------

bup has a few advantages over other backup software:

 - It uses a rolling checksum algorithm (similar to rsync) to split large
   files into chunks.  The most useful result of this is you can backup huge
   virtual machine (VM) disk images, databases, and XML files incrementally,
   even though they're typically all in one huge file, and not use tons of
   disk space for multiple versions.
   
 - It uses the packfile format from git (the open source version control
   system), so you can access the stored data even if you don't like bup's
   user interface.
   
 - Unlike git, it writes packfiles *directly* (instead of having a separate
   garbage collection / repacking stage) so it's fast even with gratuitously
   huge amounts of data.  bup's improved index formats also allow you to
   track far more filenames than git (millions) and keep track of far more
   objects (hundreds or thousands of gigabytes).
   
 - Data is "automagically" shared between incremental backups without having
   to know which backup is based on which other one - even if the backups
   are made from two different computers that don't even know about each
   other.  You just tell bup to back stuff up, and it saves only the minimum
   amount of data needed.
   
 - You can back up directly to a remote bup server, without needing tons of
   temporary disk space on the computer being backed up.  And if your backup
   is interrupted halfway through, the next run will pick up where you left
   off.  And it's easy to set up a bup server: just install bup on any
   machine where you have ssh access.
   
 - Bup can use "par2" redundancy to recover corrupted backups even if your
   disk has undetected bad sectors.
   
 - Even when a backup is incremental, you don't have to worry about
   restoring the full backup, then each of the incrementals in turn; an
   incremental backup *acts* as if it's a full backup, it just takes less
   disk space.
   
 - You can mount your bup repository as a FUSE filesystem and access the
   content that way, and even export it over Samba.
   
 - It's written in python (with some C parts to make it faster) so it's easy
   for you to extend and maintain.


Reasons you might want to avoid bup
-----------------------------------

 - It's not remotely as well tested as something like tar, so it's
   more likely to eat your data.  It's also missing some
   probably-critical features, though fewer than it used to be.
   
 - It requires python >= 2.6, a C compiler, and an installed git
   version >= 1.5.6.  It also requires par2 if you want fsck to be
   able to generate the information needed to recover from some types
   of corruption.
 
 - It currently only works on Linux, FreeBSD, NetBSD, OS X >= 10.4,
   Solaris, or Windows (with Cygwin, and maybe with WSL).  Patches to
   support other platforms are welcome.

 - Until resolved, a [glibc bug](https://sourceware.org/bugzilla/show_bug.cgi?id=26034)
   might cause bup to crash on startup for some (unusual) command line
   argument values, when bup is configured to use Python 3.

 - Any items in "Things that are stupid" below.


Notable changes introduced by a release
=======================================

 - <a href="note/0.30.1-from-0.30.md">Changes in 0.30.1 as compared to 0.30</a>
 - <a href="note/0.30-from-0.29.3.md">Changes in 0.30 as compared to 0.29.3</a>
 - <a href="note/0.29.3-from-0.29.2.md">Changes in 0.29.3 as compared to 0.29.2</a>
 - <a href="note/0.29.2-from-0.29.1.md">Changes in 0.29.2 as compared to 0.29.1</a>
 - <a href="note/0.29.1-from-0.29.md">Changes in 0.29.1 as compared to 0.29</a>
 - <a href="note/0.29-from-0.28.1.md">Changes in 0.29 as compared to 0.28.1</a>
 - <a href="note/0.28.1-from-0.28.md">Changes in 0.28.1 as compared to 0.28</a>
 - <a href="note/0.28-from-0.27.1.md">Changes in 0.28 as compared to 0.27.1</a>
 - <a href="note/0.27.1-from-0.27.md">Changes in 0.27.1 as compared to 0.27</a>


Test status
===========

| branch | Debian                                                                                                                                         | FreeBSD                                                                                                                                          | macOS                                                                                                                                        |
|--------|------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| master | [![Debian test status](https://api.cirrus-ci.com/github/bup/bup.svg?branch=master&task=debian)](https://cirrus-ci.com/github/bup/bup) | [![FreeBSD test status](https://api.cirrus-ci.com/github/bup/bup.svg?branch=master&task=freebsd)](https://cirrus-ci.com/github/bup/bup) | [![macOS test status](https://api.cirrus-ci.com/github/bup/bup.svg?branch=master&task=macos)](https://cirrus-ci.com/github/bup/bup) |
| 0.30.x | [![Debian test status](https://api.cirrus-ci.com/github/bup/bup.svg?branch=0.30.x&task=debian)](https://cirrus-ci.com/github/bup/bup) | [![FreeBSD test status](https://api.cirrus-ci.com/github/bup/bup.svg?branch=0.30.x&task=freebsd)](https://cirrus-ci.com/github/bup/bup) | [![macOS test status](https://api.cirrus-ci.com/github/bup/bup.svg?branch=0.30.x&task=macos)](https://cirrus-ci.com/github/bup/bup) |
| 0.29.x | [![Debian test status](https://api.cirrus-ci.com/github/bup/bup.svg?branch=0.29.x&task=debian)](https://cirrus-ci.com/github/bup/bup) | [![FreeBSD test status](https://api.cirrus-ci.com/github/bup/bup.svg?branch=0.29.x&task=freebsd)](https://cirrus-ci.com/github/bup/bup) | [![macOS test status](https://api.cirrus-ci.com/github/bup/bup.svg?branch=0.29.x&task=macos)](https://cirrus-ci.com/github/bup/bup) |

Getting started
===============

From source
-----------

 - Check out the bup source code using git:

    ```sh
    git clone https://github.com/bup/bup
    ```

 - This will leave you on the master branch, which is perfect if you
   would like to help with development, but if you'd just like to use
   bup, please check out the latest stable release like this:

    ```sh
    git checkout 0.29.1
    ```

   You can see the latest stable release here:
   https://github.com/bup/bup/releases.

 - Install the required python libraries (including the development
   libraries).

   On very recent Debian/Ubuntu versions, this may be sufficient (run
   as root):

    ```sh
    apt-get build-dep bup
    ```

   Otherwise try this (substitute python2.6-dev if you have an older
   system):

    ```sh
    apt-get install python2.7-dev python-fuse
    apt-get install python-pyxattr python-pylibacl
    apt-get install linux-libc-dev
    apt-get install acl attr
    apt-get install libreadline-dev # optional (bup ftp)
    apt-get install python-tornado # optional (bup web)
    ```

   On CentOS (for CentOS 6, at least), this should be sufficient (run
   as root):

    ```sh
    yum groupinstall "Development Tools"
    yum install python python-devel
    yum install fuse-python pyxattr pylibacl
    yum install perl-Time-HiRes
    yum install readline-devel # optional (bup ftp)
    yum install python-tornado # optional (bup web)
    ```

   In addition to the default CentOS repositories, you may need to add
   RPMForge (for fuse-python) and EPEL (for pyxattr and pylibacl).

   On Cygwin, install python, make, rsync, and gcc4.

   If you would like to use the optional bup web server on systems
   without a tornado package, you may want to try this:

    ```sh
    pip install tornado
    ```

 - Build the python module and symlinks:

    ```sh
    make
    ```
 	
 - Run the tests:

    ```sh
    make long-check
    ```

    or if you're in a bit more of a hurry:

    ```sh
    make check
    ```
 	
    The tests should pass.  If they don't pass for you, stop here and
    send an email to bup-list@googlegroups.com.  Though if there are
    symbolic links along the current working directory path, the tests
    may fail.  Running something like this before "make test" should
    sidestep the problem:

    ```sh
    cd "$(pwd -P)"
    ```

 - You can install bup via "make install", and override the default
   destination with DESTDIR and PREFIX.

   Files are normally installed to "$DESTDIR/$PREFIX" where DESTDIR is
   empty by default, and PREFIX is set to /usr/local.  So if you wanted to
   install bup to /opt/bup, you might do something like this:

    ```sh
    make install DESTDIR=/opt/bup PREFIX=''
    ```

 - The Python executable that bup will use is chosen by ./configure,
   which will search for a reasonable version unless PYTHON is set in
   the environment, in which case, bup will use that path.  You can
   see which Python executable was chosen by looking at the
   configure output, or examining cmd/python-cmd.sh, and you can
   change the selection by re-running ./configure.

From binary packages
--------------------

Binary packages of bup are known to be built for the following OSes:

 - Debian:
    http://packages.debian.org/search?searchon=names&keywords=bup
 - Ubuntu:
    http://packages.ubuntu.com/search?searchon=names&keywords=bup
 - pkgsrc (NetBSD, Dragonfly, and others)
    http://pkgsrc.se/sysutils/bup
    http://cvsweb.netbsd.org/bsdweb.cgi/pkgsrc/sysutils/bup/
 - Arch Linux:
    https://www.archlinux.org/packages/?sort=&q=bup
 - Fedora:
    https://apps.fedoraproject.org/packages/bup


Using bup
---------

 - Get help for any bup command:

    ```sh
    bup help
    bup help init
    bup help index
    bup help save
    bup help restore
    ...
    ```

 - Initialize the default BUP_DIR (~/.bup -- you can choose another by
   either specifying `bup -d DIR ...` or setting the `BUP_DIR`
   environment variable for a command):

    ```sh
    bup init
    ```

 - Make a local backup (-v or -vv will increase the verbosity):

    ```sh
    bup index /etc
    bup save -n local-etc /etc
    ```

 - Restore a local backup to ./dest:

    ```sh
    bup restore -C ./dest local-etc/latest/etc
    ls -l dest/etc
    ```

 - Look at how much disk space your backup took:

    ```sh
    du -s ~/.bup
    ```

 - Make another backup (which should be mostly identical to the last one;
   notice that you don't have to *specify* that this backup is incremental,
   it just saves space automatically):

    ```sh
    bup index /etc
    bup save -n local-etc /etc
    ```

 - Look how little extra space your second backup used (on top of the first):

    ```sh
    du -s ~/.bup
    ```

 - Get a list of your previous backups:

    ```sh
    bup ls local-etc
    ```

 - Restore your first backup again:

    ```sh
    bup restore -C ./dest-2 local-etc/2013-11-23-11195/etc
    ```

 - Make a backup to a remote server which must already have the 'bup' command
   somewhere in its PATH (see /etc/profile, etc/environment, ~/.profile, or
   ~/.bashrc), and be accessible via ssh.
   Make sure to replace SERVERNAME with the actual hostname of your server:

    ```sh
    bup init -r SERVERNAME:path/to/remote-bup-dir
    bup index /etc
    bup save -r SERVERNAME:path/to/remote-bup-dir -n local-etc /etc
    ```

 - Make a remote backup to ~/.bup on SERVER:

    ```sh
    bup index /etc
    bup save -r SERVER: -n local-etc /etc
    ```

 - See what saves are available in ~/.bup on SERVER:

    ```sh
    bup ls -r SERVER:
    ```

 - Restore the remote backup to ./dest:

    ```sh
    bup restore -r SERVER: -C ./dest local-etc/latest/etc
    ls -l dest/etc
    ```

 - Defend your backups from death rays (OK fine, more likely from the
   occasional bad disk block).  This writes parity information
   (currently via par2) for all of the existing data so that bup may
   be able to recover from some amount of repository corruption:

    ```sh
    bup fsck -g
    ```

 - Use split/join instead of index/save/restore.  Try making a local
   backup using tar:

    ```sh
    tar -cvf - /etc | bup split -n local-etc -vv
    ```
 	
 - Try restoring the tarball:

    ```sh
    bup join local-etc | tar -tf -
    ```
 	
 - Look at how much disk space your backup took:

    ```sh
    du -s ~/.bup
    ```
 	
 - Make another tar backup:

    ```sh
    tar -cvf - /etc | bup split -n local-etc -vv
    ```
 	
 - Look at how little extra space your second backup used on top of
   the first:

    ```sh
    du -s ~/.bup
    ```
 	
 - Restore the first tar backup again (the ~1 is git notation for "one
   older than the most recent"):

    ```sh
    bup join local-etc~1 | tar -tf -
    ```
 
 - Get a list of your previous split-based backups:

    ```sh
    GIT_DIR=~/.bup git log local-etc
    ```
	
 - Save a tar archive to a remote server (without tar -z to facilitate
   deduplication):

    ```sh
    tar -cvf - /etc | bup split -r SERVERNAME: -n local-etc -vv
    ```
 
 - Restore the archive:

    ```sh
    bup join -r SERVERNAME: local-etc | tar -tf -
    ```
 	
That's all there is to it!


Notes on FreeBSD
----------------

- FreeBSD's default 'make' command doesn't like bup's Makefile. In order to
  compile the code, run tests and install bup, you need to install GNU Make
  from the port named 'gmake' and use its executable instead in the commands
  seen above. (i.e. 'gmake test' runs bup's test suite)

- Python's development headers are automatically installed with the 'python'
  port so there's no need to install them separately.

- To use the 'bup fuse' command, you need to install the fuse kernel module
  from the 'fusefs-kmod' port in the 'sysutils' section and the libraries from
  the port named 'py-fusefs' in the 'devel' section.

- The 'par2' command can be found in the port named 'par2cmdline'.

- In order to compile the documentation, you need pandoc which can be found in
  the port named 'hs-pandoc' in the 'textproc' section.


Notes on NetBSD/pkgsrc
----------------------

 - See pkgsrc/sysutils/bup, which should be the most recent stable
   release and includes man pages.  It also has a reasonable set of
   dependencies (git, par2, py-fuse-bindings).

 - The "fuse-python" package referred to is hard to locate, and is a
   separate tarball for the python language binding distributed by the
   fuse project on sourceforge.  It is available as
   pkgsrc/filesystems/py-fuse-bindings and on NetBSD 5, "bup fuse"
   works with it.

 - "bup fuse" presents every directory/file as inode 0.  The directory
   traversal code ("fts") in NetBSD's libc will interpret this as a
   cycle and error out, so "ls -R" and "find" will not work.

 - There is no support for ACLs.  If/when some enterprising person
   fixes this, adjust t/compare-trees.


Notes on Cygwin
---------------

 - There is no support for ACLs.  If/when some enterprising person
   fixes this, adjust t/compare-trees.

 - In t/test.sh, two tests have been disabled.  These tests check to
   see that repeated saves produce identical trees and that an
   intervening index doesn't change the SHA1.  Apparently Cygwin has
   some unusual behaviors with respect to access times (that probably
   warrant further investigation).  Possibly related:
   http://cygwin.com/ml/cygwin/2007-06/msg00436.html


Notes on OS X
-------------

 - There is no support for ACLs.  If/when some enterprising person
   fixes this, adjust t/compare-trees.


How it works
============

Basic storage:
--------------

bup stores its data in a git-formatted repository.  Unfortunately, git
itself doesn't actually behave very well for bup's use case (huge numbers of
files, files with huge sizes, retaining file permissions/ownership are
important), so we mostly don't use git's *code* except for a few helper
programs.  For example, bup has its own git packfile writer written in
python.

Basically, 'bup split' reads the data on stdin (or from files specified on
the command line), breaks it into chunks using a rolling checksum (similar to
rsync), and saves those chunks into a new git packfile.  There is at least one
git packfile per backup.

When deciding whether to write a particular chunk into the new packfile, bup
first checks all the other packfiles that exist to see if they already have that
chunk.  If they do, the chunk is skipped.

git packs come in two parts: the pack itself (*.pack) and the index (*.idx).
The index is pretty small, and contains a list of all the objects in the
pack.  Thus, when generating a remote backup, we don't have to have a copy
of the packfiles from the remote server: the local end just downloads a copy
of the server's *index* files, and compares objects against those when
generating the new pack, which it sends directly to the server.

The "-n" option to 'bup split' and 'bup save' is the name of the backup you
want to create, but it's actually implemented as a git branch.  So you can
do cute things like checkout a particular branch using git, and receive a
bunch of chunk files corresponding to the file you split.

If you use '-b' or '-t' or '-c' instead of '-n', bup split will output a
list of blobs, a tree containing that list of blobs, or a commit containing
that tree, respectively, to stdout.  You can use this to construct your own
scripts that do something with those values.

The bup index:
--------------

'bup index' walks through your filesystem and updates a file (whose name is,
by default, ~/.bup/bupindex) to contain the name, attributes, and an
optional git SHA1 (blob id) of each file and directory.

'bup save' basically just runs the equivalent of 'bup split' a whole bunch
of times, once per file in the index, and assembles a git tree
that contains all the resulting objects.  Among other things, that makes
'git diff' much more useful (compared to splitting a tarball, which is
essentially a big binary blob).  However, since bup splits large files into
smaller chunks, the resulting tree structure doesn't *exactly* correspond to
what git itself would have stored.  Also, the tree format used by 'bup save'
will probably change in the future to support storing file ownership, more
complex file permissions, and so on.

If a file has previously been written by 'bup save', then its git blob/tree
id is stored in the index.  This lets 'bup save' avoid reading that file to
produce future incremental backups, which means it can go *very* fast unless
a lot of files have changed.

 
Things that are stupid for now but which we'll fix later
========================================================

Help with any of these problems, or others, is very welcome.  Join the
mailing list (see below) if you'd like to help.

 - 'bup save' and 'bup restore' have immature metadata support.
 
    On the plus side, they actually do have support now, but it's new,
    and not remotely as well tested as tar/rsync/whatever's.  However,
    you have to start somewhere, and as of 0.25, we think it's ready
    for more general use.  Please let us know if you have any trouble.

    Also, if any strip or graft-style options are specified to 'bup
    save', then no metadata will be written for the root directory.
    That's obviously less than ideal.

 - bup is overly optimistic about mmap.  Right now bup just assumes
   that it can mmap as large a block as it likes, and that mmap will
   never fail.  Yeah, right... If nothing else, this has failed on
   32-bit architectures (and 31-bit is even worse -- looking at you,
   s390).

   To fix this, we might just implement a FakeMmap[1] class that uses
   normal file IO and handles all of the mmap methods[2] that bup
   actually calls.  Then we'd swap in one of those whenever mmap
   fails.

   This would also require implementing some of the methods needed to
   support "[]" array access, probably at a minimum __getitem__,
   __setitem__, and __setslice__ [3].

     [1] http://comments.gmane.org/gmane.comp.sysutils.backup.bup/613
     [2] http://docs.python.org/2/library/mmap.html
     [3] http://docs.python.org/2/reference/datamodel.html#emulating-container-types

 - 'bup index' is slower than it should be.
 
    It's still rather fast: it can iterate through all the filenames on my
    600,000 file filesystem in a few seconds.  But it still needs to rewrite
    the entire index file just to add a single filename, which is pretty
    nasty; it should just leave the new files in a second "extra index" file
    or something.
   
 - bup could use inotify for *really* efficient incremental backups.

    You could even have your system doing "continuous" backups: whenever a
    file changes, we immediately send an image of it to the server.  We could
    give the continuous-backup process a really low CPU and I/O priority so
    you wouldn't even know it was running.

 - bup only has experimental support for pruning old backups.

   While you should now be able to drop old saves and branches with
   `bup rm`, and reclaim the space occupied by data that's no longer
   needed by other backups with `bup gc`, these commands are
   experimental, and should be handled with great care.  See the
   man pages for more information.

   Unless you want to help test the new commands, one possible
   workaround is to just start a new BUP_DIR occasionally,
   i.e. bup-2013, bup-2014...

 - bup has never been tested on anything but Linux, FreeBSD, NetBSD,
   OS X, and Windows+Cygwin.
 
    There's nothing that makes it *inherently* non-portable, though, so
    that's mostly a matter of someone putting in some effort.  (For a
    "native" Windows port, the most annoying thing is the absence of ssh in
    a default Windows installation.)
    
 - bup needs better documentation.
 
    According to an article about bup in Linux Weekly News
    (https://lwn.net/Articles/380983/), "it's a bit short on examples and
    a user guide would be nice."  Documentation is the sort of thing that
    will never be great unless someone from outside contributes it (since
    the developers can never remember which parts are hard to understand).
    
 - bup is "relatively speedy" and has "pretty good" compression.
 
    ...according to the same LWN article.  Clearly neither of those is good
    enough.  We should have awe-inspiring speed and crazy-good compression. 
    Must work on that.  Writing more parts in C might help with the speed.
   
 - bup has no GUI.
 
   Actually, that's not stupid, but you might consider it a
   limitation.  See the ["Related Projects"](https://bup.github.io/)
   list for some possible options.
    
More Documentation
==================

bup has an extensive set of man pages.  Try using 'bup help' to get
started, or use 'bup help SUBCOMMAND' for any bup subcommand (like split,
join, index, save, etc.) to get details on that command.

For further technical details, please see ./DESIGN.


How you can help
================

bup is a work in progress and there are many ways it can still be improved.
If you'd like to contribute patches, ideas, or bug reports, please join the
bup mailing list.

You can find the mailing list archives here:

	http://groups.google.com/group/bup-list
	
and you can subscribe by sending a message to:

	bup-list+subscribe@googlegroups.com

Please see <a href="HACKING">./HACKING</a> for
additional information, i.e. how to submit patches (hint - no pull
requests), how we handle branches, etc.


Have fun,

Avery
