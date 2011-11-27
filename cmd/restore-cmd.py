#!/usr/bin/env python
import sys, stat
from bup import options, git, metadata, vfs
from bup.helpers import *

optspec = """
bup restore [-C outdir] </branch/revision/path/to/dir ...>
--
C,outdir=   change to given outdir before extracting files
numeric-ids restore numeric IDs (user, group, etc.) rather than names
v,verbose   increase log output (can be used more than once)
q,quiet     don't show progress meter
"""

total_restored = 0


def verbose1(s):
    if opt.verbose >= 1:
        print s


def verbose2(s):
    if opt.verbose >= 2:
        print s


def plog(s):
    if opt.quiet:
        return
    qprogress(s)


def print_info(n, fullname):
    if stat.S_ISDIR(n.mode):
        verbose1('%s/' % fullname)
    elif stat.S_ISLNK(n.mode):
        verbose2('%s@ -> %s' % (fullname, n.readlink()))
    else:
        verbose2(fullname)


def create_path(n, fullname, meta):
    if meta:
        meta.create_path(fullname)
    else:
        # These fallbacks are important -- meta could be null if, for
        # example, save created a "fake" item, i.e. a new strip/graft
        # path element, etc.  You can find cases like that by
        # searching for "Metadata()".
        unlink(fullname)
        if stat.S_ISDIR(n.mode):
            mkdirp(fullname)
        elif stat.S_ISLNK(n.mode):
            os.symlink(n.readlink(), fullname)


def do_node(top, n, meta=None):
    # meta will be None for dirs, and when there is no .bupm (i.e. no metadata)
    global total_restored, opt
    meta_stream = None
    try:
        fullname = n.fullname(stop_at=top)
        # If this is a directory, its metadata is the first entry in
        # any .bupm file inside the directory.  Get it.
        if(stat.S_ISDIR(n.mode)):
            mfile = n.metadata_file() # VFS file -- cannot close().
            if mfile:
                meta_stream = mfile.open()
                meta = metadata.Metadata.read(meta_stream)
        print_info(n, fullname)
        create_path(n, fullname, meta)

        # Write content if appropriate (only regular files have content).
        plain_file = False
        if meta:
            plain_file = stat.S_ISREG(meta.mode)
        else:
            plain_file = stat.S_ISREG(n.mode)

        if plain_file:
            outf = open(fullname, 'wb')
            try:
                for b in chunkyreader(n.open()):
                    outf.write(b)
            finally:
                outf.close()

        total_restored += 1
        plog('Restoring: %d\r' % total_restored)
        for sub in n:
            m = None
            # Don't get metadata if this is a dir -- handled in sub do_node().
            if meta_stream and not stat.S_ISDIR(sub.mode):
                m = metadata.Metadata.read(meta_stream)
            do_node(top, sub, m)
        if meta:
            meta.apply_to_path(fullname,
                               restore_numeric_ids=opt.numeric_ids)
    finally:
        if meta_stream:
            meta_stream.close()

handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()
top = vfs.RefList(None)

if not extra:
    o.fatal('must specify at least one filename to restore')
    
if opt.outdir:
    mkdirp(opt.outdir)
    os.chdir(opt.outdir)

ret = 0
for d in extra:
    path,name = os.path.split(d)
    try:
        n = top.lresolve(d)
    except vfs.NodeError, e:
        add_error(e)
        continue
    isdir = stat.S_ISDIR(n.mode)
    if not name or name == '.':
        # trailing slash: extract children to cwd
        if not isdir:
            add_error('%r: not a directory' % d)
        else:
            for sub in n:
                do_node(n, sub)
    else:
        # no trailing slash: extract node and its children to cwd
        do_node(n.parent, n)

if not opt.quiet:
    progress('Restoring: %d, done.\n' % total_restored)

if saved_errors:
    log('WARNING: %d errors encountered while restoring.\n' % len(saved_errors))
    sys.exit(1)
