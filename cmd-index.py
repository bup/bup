#!/usr/bin/env python
import os, sys, stat, time
import options, git, index, drecurse
from helpers import *


def merge_indexes(out, r1, r2):
    log('bup: merging indexes.\n')
    for e in index._last_writer_wins_iter([r1, r2]):
        #if e.flags & index.IX_EXISTS:
            out.add_ixentry(e)


class IterHelper:
    def __init__(self, l):
        self.i = iter(l)
        self.cur = None
        self.next()

    def next(self):
        try:
            self.cur = self.i.next()
        except StopIteration:
            self.cur = None
        return self.cur


def update_index(top):
    ri = index.Reader(indexfile)
    wi = index.Writer(indexfile)
    rig = IterHelper(ri.iter(name=top))
    tstart = int(time.time())

    hashgen = None
    if opt.fake_valid:
        def hashgen(name):
            return (0, index.FAKE_SHA)

    #log('doing: %r\n' % paths)

    for (path,pst) in drecurse.recursive_dirlist([top], xdev=opt.xdev):
        #log('got: %r\n' % path)
        if opt.verbose>=2 or (opt.verbose==1 and stat.S_ISDIR(pst.st_mode)):
            sys.stdout.write('%s\n' % path)
            sys.stdout.flush()
        while rig.cur and rig.cur.name > path:  # deleted paths
            rig.cur.set_deleted()
            rig.cur.repack()
            rig.next()
        if rig.cur and rig.cur.name == path:    # paths that already existed
            if pst:
                rig.cur.from_stat(pst, tstart)
            if not (rig.cur.flags & index.IX_HASHVALID):
                if hashgen:
                    (rig.cur.gitmode, rig.cur.sha) = hashgen(path)
                    rig.cur.flags |= index.IX_HASHVALID
                rig.cur.repack()
            rig.next()
        else:  # new paths
            #log('adding: %r\n' % path)
            wi.add(path, pst, hashgen = hashgen)
    
    if ri.exists():
        ri.save()
        wi.flush()
        if wi.count:
            mi = index.Writer(indexfile)
            merge_indexes(mi, ri, wi.new_reader())
            ri.close()
            mi.close()
        wi.abort()
    else:
        wi.close()


optspec = """
bup index <-p|s|m|u> [options...] <filenames...>
--
p,print    print the index entries for the given names (also works with -u)
m,modified print only added/deleted/modified files (implies -p)
s,status   print each filename with a status char (A/M/D) (implies -p)
H,hash     print the hash for each object next to its name (implies -p)
u,update   (recursively) update the index entries for the given filenames
x,xdev,one-file-system  don't cross filesystem boundaries
fake-valid    mark all index entries as up-to-date even if they aren't
f,indexfile=  the name of the index file (default 'index')
v,verbose  increase log output (can be used more than once)
"""
o = options.Options('bup index', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if not (opt.modified or opt['print'] or opt.status or opt.update):
    log('bup index: you must supply one or more of -p, -s, -m, or -u\n')
    o.usage()
if opt.fake_valid and not opt.update:
    log('bup index: --fake-valid is meaningless without -u\n')
    o.usage()

git.check_repo_or_die()
indexfile = opt.indexfile or git.repo('bupindex')

paths = index.reduce_paths(extra)

if opt.update:
    if not paths:
        log('bup index: update (-u) requested but no paths given\n')
        o.usage()
    for (rp,path) in paths:
        update_index(rp)

if opt['print'] or opt.status or opt.modified:
    for (name, ent) in index.Reader(indexfile).filter(extra or ['']):
        if opt.modified and (ent.flags & index.IX_HASHVALID
                             or stat.S_ISDIR(ent.mode)):
            continue
        line = ''
        if opt.status:
            if not ent.flags & index.IX_EXISTS:
                line += 'D '
            elif not ent.flags & index.IX_HASHVALID:
                if ent.sha == index.EMPTY_SHA:
                    line += 'A '
                else:
                    line += 'M '
            else:
                line += '  '
        if opt.hash:
            line += ent.sha.encode('hex') + ' '
        print line + (name or './')
        #print repr(ent)

if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    sys.exit(1)
