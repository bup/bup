#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import, print_function
from binascii import hexlify
import sys, stat, time, os, errno, re

from bup import metadata, options, git, index, drecurse, hlinkdb
from bup.compat import argv_bytes
from bup.drecurse import recursive_dirlist
from bup.hashsplit import GIT_MODE_TREE, GIT_MODE_FILE
from bup.helpers import (add_error, handle_ctrl_c, log, parse_excludes, parse_rx_excludes,
                         progress, qprogress, saved_errors)
from bup.io import byte_stream, path_msg


class IterHelper:
    def __init__(self, l):
        self.i = iter(l)
        self.cur = None
        self.next()

    def __next__(self):
        self.cur = next(self.i, None)
        return self.cur

    next = __next__

def check_index(reader):
    try:
        log('check: checking forward iteration...\n')
        e = None
        d = {}
        for e in reader.forward_iter():
            if e.children_n:
                if opt.verbose:
                    log('%08x+%-4d %r\n' % (e.children_ofs, e.children_n,
                                            path_msg(e.name)))
                assert(e.children_ofs)
                assert e.name.endswith(b'/')
                assert(not d.get(e.children_ofs))
                d[e.children_ofs] = 1
            if e.flags & index.IX_HASHVALID:
                assert(e.sha != index.EMPTY_SHA)
                assert(e.gitmode)
        assert not e or bytes(e.name) == b'/'  # last entry is *always* /
        log('check: checking normal iteration...\n')
        last = None
        for e in reader:
            if last:
                assert(last > e.name)
            last = e.name
    except:
        log('index error! at %r\n' % e)
        raise
    log('check: passed.\n')


def clear_index(indexfile):
    indexfiles = [indexfile, indexfile + b'.meta', indexfile + b'.hlink']
    for indexfile in indexfiles:
        path = git.repo(indexfile)
        try:
            os.remove(path)
            if opt.verbose:
                log('clear: removed %s\n' % path_msg(path))
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise


def update_index(top, excluded_paths, exclude_rxs, xdev_exceptions, out=None):
    # tmax and start must be epoch nanoseconds.
    tmax = (time.time() - 1) * 10**9
    ri = index.Reader(indexfile)
    msw = index.MetaStoreWriter(indexfile + b'.meta')
    wi = index.Writer(indexfile, msw, tmax)
    rig = IterHelper(ri.iter(name=top))
    tstart = int(time.time()) * 10**9

    hlinks = hlinkdb.HLinkDB(indexfile + b'.hlink')

    fake_hash = None
    if opt.fake_valid:
        def fake_hash(name):
            return (GIT_MODE_FILE, index.FAKE_SHA)

    total = 0
    bup_dir = os.path.abspath(git.repo())
    index_start = time.time()
    for path, pst in recursive_dirlist([top],
                                       xdev=opt.xdev,
                                       bup_dir=bup_dir,
                                       excluded_paths=excluded_paths,
                                       exclude_rxs=exclude_rxs,
                                       xdev_exceptions=xdev_exceptions):
        if opt.verbose>=2 or (opt.verbose==1 and stat.S_ISDIR(pst.st_mode)):
            out.write(b'%s\n' % path)
            out.flush()
            elapsed = time.time() - index_start
            paths_per_sec = total / elapsed if elapsed else 0
            qprogress('Indexing: %d (%d paths/s)\r' % (total, paths_per_sec))
        elif not (total % 128):
            elapsed = time.time() - index_start
            paths_per_sec = total / elapsed if elapsed else 0
            qprogress('Indexing: %d (%d paths/s)\r' % (total, paths_per_sec))
        total += 1

        while rig.cur and rig.cur.name > path:  # deleted paths
            if rig.cur.exists():
                rig.cur.set_deleted()
                rig.cur.repack()
                if rig.cur.nlink > 1 and not stat.S_ISDIR(rig.cur.mode):
                    hlinks.del_path(rig.cur.name)
            rig.next()

        if rig.cur and rig.cur.name == path:    # paths that already existed
            need_repack = False
            if(rig.cur.stale(pst, tstart, check_device=opt.check_device)):
                try:
                    meta = metadata.from_path(path, statinfo=pst)
                except (OSError, IOError) as e:
                    add_error(e)
                    rig.next()
                    continue
                if not stat.S_ISDIR(rig.cur.mode) and rig.cur.nlink > 1:
                    hlinks.del_path(rig.cur.name)
                if not stat.S_ISDIR(pst.st_mode) and pst.st_nlink > 1:
                    hlinks.add_path(path, pst.st_dev, pst.st_ino)
                # Clear these so they don't bloat the store -- they're
                # already in the index (since they vary a lot and they're
                # fixed length).  If you've noticed "tmax", you might
                # wonder why it's OK to do this, since that code may
                # adjust (mangle) the index mtime and ctime -- producing
                # fake values which must not end up in a .bupm.  However,
                # it looks like that shouldn't be possible:  (1) When
                # "save" validates the index entry, it always reads the
                # metadata from the filesytem. (2) Metadata is only
                # read/used from the index if hashvalid is true. (3)
                # "faked" entries will be stale(), and so we'll invalidate
                # them below.
                meta.ctime = meta.mtime = meta.atime = 0
                meta_ofs = msw.store(meta)
                rig.cur.update_from_stat(pst, meta_ofs)
                rig.cur.invalidate()
                need_repack = True
            if not (rig.cur.flags & index.IX_HASHVALID):
                if fake_hash:
                    if rig.cur.sha == index.EMPTY_SHA:
                        rig.cur.gitmode, rig.cur.sha = fake_hash(path)
                    rig.cur.flags |= index.IX_HASHVALID
                    need_repack = True
            if opt.fake_invalid:
                rig.cur.invalidate()
                need_repack = True
            if need_repack:
                rig.cur.repack()
            rig.next()
        else:  # new paths
            try:
                meta = metadata.from_path(path, statinfo=pst)
            except (OSError, IOError) as e:
                add_error(e)
                continue
            # See same assignment to 0, above, for rationale.
            meta.atime = meta.mtime = meta.ctime = 0
            meta_ofs = msw.store(meta)
            wi.add(path, pst, meta_ofs, hashgen=fake_hash)
            if not stat.S_ISDIR(pst.st_mode) and pst.st_nlink > 1:
                hlinks.add_path(path, pst.st_dev, pst.st_ino)

    elapsed = time.time() - index_start
    paths_per_sec = total / elapsed if elapsed else 0
    progress('Indexing: %d, done (%d paths/s).\n' % (total, paths_per_sec))

    hlinks.prepare_save()

    if ri.exists():
        ri.save()
        wi.flush()
        if wi.count:
            wr = wi.new_reader()
            if opt.check:
                log('check: before merging: oldfile\n')
                check_index(ri)
                log('check: before merging: newfile\n')
                check_index(wr)
            mi = index.Writer(indexfile, msw, tmax)

            for e in index.merge(ri, wr):
                # FIXME: shouldn't we remove deleted entries eventually?  When?
                mi.add_ixentry(e)

            ri.close()
            mi.close()
            wr.close()
        wi.abort()
    else:
        wi.close()

    msw.close()
    hlinks.commit_save()


optspec = """
bup index <-p|-m|-s|-u|--clear|--check> [options...] <filenames...>
--
 Modes:
p,print    print the index entries for the given names (also works with -u)
m,modified print only added/deleted/modified files (implies -p)
s,status   print each filename with a status char (A/M/D) (implies -p)
u,update   recursively update the index entries for the given file/dir names (default if no mode is specified)
check      carefully check index file integrity
clear      clear the default index
 Options:
H,hash     print the hash for each object next to its name
l,long     print more information about each file
no-check-device don't invalidate an entry if the containing device changes
fake-valid mark all index entries as up-to-date even if they aren't
fake-invalid mark all index entries as invalid
f,indexfile=  the name of the index file (normally BUP_DIR/bupindex)
exclude= a path to exclude from the backup (may be repeated)
exclude-from= skip --exclude paths in file (may be repeated)
exclude-rx= skip paths matching the unanchored regex (may be repeated)
exclude-rx-from= skip --exclude-rx patterns in file (may be repeated)
v,verbose  increase log output (can be used more than once)
x,xdev,one-file-system  don't cross filesystem boundaries
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if not (opt.modified or \
        opt['print'] or \
        opt.status or \
        opt.update or \
        opt.check or \
        opt.clear):
    opt.update = 1
if (opt.fake_valid or opt.fake_invalid) and not opt.update:
    o.fatal('--fake-{in,}valid are meaningless without -u')
if opt.fake_valid and opt.fake_invalid:
    o.fatal('--fake-valid is incompatible with --fake-invalid')
if opt.clear and opt.indexfile:
    o.fatal('cannot clear an external index (via -f)')

# FIXME: remove this once we account for timestamp races, i.e. index;
# touch new-file; index.  It's possible for this to happen quickly
# enough that new-file ends up with the same timestamp as the first
# index, and then bup will ignore it.
tick_start = time.time()
time.sleep(1 - (tick_start - int(tick_start)))

git.check_repo_or_die()

handle_ctrl_c()

if opt.verbose is None:
    opt.verbose = 0

if opt.indexfile:
    indexfile = argv_bytes(opt.indexfile)
else:
    indexfile = git.repo(b'bupindex')

if opt.check:
    log('check: starting initial check.\n')
    check_index(index.Reader(indexfile))

if opt.clear:
    log('clear: clearing index.\n')
    clear_index(indexfile)

sys.stdout.flush()
out = byte_stream(sys.stdout)

if opt.update:
    if not extra:
        o.fatal('update mode (-u) requested but no paths given')
    extra = [argv_bytes(x) for x in extra]
    excluded_paths = parse_excludes(flags, o.fatal)
    exclude_rxs = parse_rx_excludes(flags, o.fatal)
    xexcept = index.unique_resolved_paths(extra)
    for rp, path in index.reduce_paths(extra):
        update_index(rp, excluded_paths, exclude_rxs, xdev_exceptions=xexcept,
                     out=out)

if opt['print'] or opt.status or opt.modified:
    extra = [argv_bytes(x) for x in extra]
    for name, ent in index.Reader(indexfile).filter(extra or [b'']):
        if (opt.modified 
            and (ent.is_valid() or ent.is_deleted() or not ent.mode)):
            continue
        line = b''
        if opt.status:
            if ent.is_deleted():
                line += b'D '
            elif not ent.is_valid():
                if ent.sha == index.EMPTY_SHA:
                    line += b'A '
                else:
                    line += b'M '
            else:
                line += b'  '
        if opt.hash:
            line += hexlify(ent.sha) + b' '
        if opt.long:
            line += b'%7s %7s ' % (oct(ent.mode), oct(ent.gitmode))
        out.write(line + (name or b'./') + b'\n')

if opt.check and (opt['print'] or opt.status or opt.modified or opt.update):
    log('check: starting final check.\n')
    check_index(index.Reader(indexfile))

if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    sys.exit(1)
