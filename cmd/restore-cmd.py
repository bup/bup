#!/usr/bin/env python
import sys, stat, time
from bup import options, git, vfs
from bup.helpers import *

optspec = """
bup restore [-C outdir] </branch/revision/path/to/dir ...>
--
C,outdir=  change to given outdir before extracting files
v,verbose  increase log output (can be used more than once)
q,quiet    don't show progress meter
"""

total_restored = last_progress = 0


def verbose1(s):
    global last_progress
    if opt.verbose >= 1:
        print s
        last_progress = 0


def verbose2(s):
    global last_progress
    if opt.verbose >= 2:
        print s
        last_progress = 0


def plog(s):
    global last_progress
    if opt.quiet:
        return
    now = time.time()
    if now - last_progress > 0.2:
        progress(s)
        last_progress = now


def do_node(top, n):
    global total_restored
    fullname = n.fullname(stop_at=top)
    unlink(fullname)
    if stat.S_ISDIR(n.mode):
        verbose1('%s/' % fullname)
        mkdirp(fullname)
    elif stat.S_ISLNK(n.mode):
        verbose2('%s@ -> %s' % (fullname, n.readlink()))
        os.symlink(n.readlink(), fullname)
    else:
        verbose2(fullname)
        outf = open(fullname, 'wb')
        try:
            for b in chunkyreader(n.open()):
                outf.write(b)
        finally:
            outf.close()
    total_restored += 1
    plog('Restoring: %d\r' % total_restored)
    for sub in n:
        do_node(top, sub)

        
handle_ctrl_c()

o = options.Options('bup restore', optspec)
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
    log('Restoring: %d, done.\n' % total_restored)

if saved_errors:
    log('WARNING: %d errors encountered while restoring.\n' % len(saved_errors))
    sys.exit(1)
