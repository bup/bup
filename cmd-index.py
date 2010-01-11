#!/usr/bin/env python2.5
import os, sys, stat
import options, git, index
from helpers import *


try:
    O_LARGEFILE = os.O_LARGEFILE
except AttributeError:
    O_LARGEFILE = 0


class OsFile:
    def __init__(self, path):
        self.fd = None
        self.fd = os.open(path, os.O_RDONLY|O_LARGEFILE|os.O_NOFOLLOW)
        
    def __del__(self):
        if self.fd:
            fd = self.fd
            self.fd = None
            os.close(fd)

    def fchdir(self):
        os.fchdir(self.fd)


saved_errors = []
def add_error(e):
    saved_errors.append(e)
    log('\n%s\n' % e)


# the use of fchdir() and lstat() are for two reasons:
#  - help out the kernel by not making it repeatedly look up the absolute path
#  - avoid race conditions caused by doing listdir() on a changing symlink
def handle_path(ri, wi, dir, name, pst, xdev, can_delete_siblings):
    hashgen = None
    if opt.fake_valid:
        def hashgen(name):
            return (0, index.FAKE_SHA)
    
    dirty = 0
    path = dir + name
    #log('handle_path(%r,%r)\n' % (dir, name))
    if stat.S_ISDIR(pst.st_mode):
        if opt.verbose == 1: # log dirs only
            sys.stdout.write('%s\n' % path)
            sys.stdout.flush()
        try:
            OsFile(name).fchdir()
        except OSError, e:
            add_error(Exception('in %s: %s' % (dir, str(e))))
            return 0
        try:
            try:
                ld = os.listdir('.')
                #log('* %r: %r\n' % (name, ld))
            except OSError, e:
                add_error(Exception('in %s: %s' % (path, str(e))))
                return 0
            lds = []
            for p in ld:
                try:
                    st = os.lstat(p)
                except OSError, e:
                    add_error(Exception('in %s: %s' % (path, str(e))))
                    continue
                if xdev != None and st.st_dev != xdev:
                    log('Skipping %r: different filesystem.\n' 
                        % index.realpath(p))
                    continue
                if stat.S_ISDIR(st.st_mode):
                    p = slashappend(p)
                lds.append((p, st))
            for p,st in reversed(sorted(lds)):
                dirty += handle_path(ri, wi, path, p, st, xdev,
                                     can_delete_siblings = True)
        finally:
            os.chdir('..')
    #log('endloop: ri.cur:%r path:%r\n' % (ri.cur.name, path))
    while ri.cur and ri.cur.name > path:
        #log('ricur:%r path:%r\n' % (ri.cur, path))
        if can_delete_siblings and dir and ri.cur.name.startswith(dir):
            #log('    --- deleting\n')
            ri.cur.flags &= ~(index.IX_EXISTS | index.IX_HASHVALID)
            ri.cur.repack()
            dirty += 1
        ri.next()
    if ri.cur and ri.cur.name == path:
        dirty += ri.cur.from_stat(pst)
        if dirty or not (ri.cur.flags & index.IX_HASHVALID):
            #log('   --- updating %r\n' % path)
            if hashgen:
                (ri.cur.gitmode, ri.cur.sha) = hashgen(name)
                ri.cur.flags |= index.IX_HASHVALID
            ri.cur.repack()
        ri.next()
    else:
        wi.add(path, pst, hashgen = hashgen)
        dirty += 1
    if opt.verbose > 1:  # all files, not just dirs
        sys.stdout.write('%s\n' % path)
        sys.stdout.flush()
    return dirty


def merge_indexes(out, r1, r2):
    log('bup: merging indexes.\n')
    for e in index._last_writer_wins_iter([r1, r2]):
        #if e.flags & index.IX_EXISTS:
            out.add_ixentry(e)


class MergeGetter:
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


def update_index(path):
    ri = index.Reader(indexfile)
    wi = index.Writer(indexfile)
    rig = MergeGetter(ri)
    
    rpath = index.realpath(path)
    st = os.lstat(rpath)
    if opt.xdev:
        xdev = st.st_dev
    else:
        xdev = None
    f = OsFile('.')
    if rpath[-1] == '/':
        rpath = rpath[:-1]
    (dir, name) = os.path.split(rpath)
    dir = slashappend(dir)
    if stat.S_ISDIR(st.st_mode) and (not rpath or rpath[-1] != '/'):
        name += '/'
        can_delete_siblings = True
    else:
        can_delete_siblings = False
    OsFile(dir or '/').fchdir()
    dirty = handle_path(rig, wi, dir, name, st, xdev, can_delete_siblings)

    # make sure all the parents of the updated path exist and are invalidated
    # if appropriate.
    while 1:
        (rpath, junk) = os.path.split(rpath)
        if not rpath:
            break
        elif rpath == '/':
            p = rpath
        else:
            p = rpath + '/'
        while rig.cur and rig.cur.name > p:
            #log('FINISHING: %r path=%r d=%r\n' % (rig.cur.name, p, dirty))
            rig.next()
        if rig.cur and rig.cur.name == p:
            if dirty:
                rig.cur.flags &= ~index.IX_HASHVALID
                rig.cur.repack()
        else:
            wi.add(p, os.lstat(p))
        if p == '/':
            break
    
    f.fchdir()
    ri.save()
    if wi.count:
        mi = index.Writer(indexfile)
        merge_indexes(mi, ri, wi.new_reader())
        ri.close()
        mi.close()
    wi.abort()


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
    for (rp, path) in paths:
        update_index(rp)

if opt['print'] or opt.status or opt.modified:
    for (name, ent) in index.Reader(indexfile).filter(extra or ['']):
        if opt.modified and ent.flags & index.IX_HASHVALID:
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
    exit(1)
