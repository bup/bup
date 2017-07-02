#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import print_function
from stat import S_ISDIR
import copy, errno, os, sys, stat, re

from bup import options, git, metadata, vfs2
from bup._helpers import write_sparsely
from bup.compat import wrap_main
from bup.helpers import (add_error, chunkyreader, die_if_errors, handle_ctrl_c,
                         log, mkdirp, parse_rx_excludes, progress, qprogress,
                         saved_errors, should_rx_exclude_path, unlink)
from bup.repo import LocalRepo


optspec = """
bup restore [-C outdir] </branch/revision/path/to/dir ...>
--
C,outdir=   change to given outdir before extracting files
numeric-ids restore numeric IDs (user, group, etc.) rather than names
exclude-rx= skip paths matching the unanchored regex (may be repeated)
exclude-rx-from= skip --exclude-rx patterns in file (may be repeated)
sparse      create sparse files
v,verbose   increase log output (can be used more than once)
map-user=   given OLD=NEW, restore OLD user as NEW user
map-group=  given OLD=NEW, restore OLD group as NEW group
map-uid=    given OLD=NEW, restore OLD uid as NEW uid
map-gid=    given OLD=NEW, restore OLD gid as NEW gid
q,quiet     don't show progress meter
"""

total_restored = 0

# stdout should be flushed after each line, even when not connected to a tty
sys.stdout.flush()
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)

def valid_restore_path(path):
    path = os.path.normpath(path)
    if path.startswith('/'):
        path = path[1:]
    if '/' in path:
        return True

def parse_owner_mappings(type, options, fatal):
    """Traverse the options and parse all --map-TYPEs, or call Option.fatal()."""
    opt_name = '--map-' + type
    value_rx = r'^([^=]+)=([^=]*)$'
    if type in ('uid', 'gid'):
        value_rx = r'^(-?[0-9]+)=(-?[0-9]+)$'
    owner_map = {}
    for flag in options:
        (option, parameter) = flag
        if option != opt_name:
            continue
        match = re.match(value_rx, parameter)
        if not match:
            raise fatal("couldn't parse %s as %s mapping" % (parameter, type))
        old_id, new_id = match.groups()
        if type in ('uid', 'gid'):
            old_id = int(old_id)
            new_id = int(new_id)
        owner_map[old_id] = new_id
    return owner_map

def apply_metadata(meta, name, restore_numeric_ids, owner_map):
    m = copy.deepcopy(meta)
    m.user = owner_map['user'].get(m.user, m.user)
    m.group = owner_map['group'].get(m.group, m.group)
    m.uid = owner_map['uid'].get(m.uid, m.uid)
    m.gid = owner_map['gid'].get(m.gid, m.gid)
    m.apply_to_path(name, restore_numeric_ids = restore_numeric_ids)
    
def hardlink_compatible(prev_path, prev_item, new_item, top):
    prev_candidate = top + prev_path
    if not os.path.exists(prev_candidate):
        return False
    prev_meta, new_meta = prev_item.meta, new_item.meta
    if new_item.oid != prev_item.oid \
            or new_meta.mtime != prev_meta.mtime \
            or new_meta.ctime != prev_meta.ctime \
            or new_meta.mode != prev_meta.mode:
        return False
    # FIXME: should we be checking the path on disk, or the recorded metadata?
    # The exists() above might seem to suggest the former.
    if not new_meta.same_file(prev_meta):
        return False
    return True

def hardlink_if_possible(fullname, item, top, hardlinks):
    """Find a suitable hardlink target, link to it, and return true,
    otherwise return false."""
    # The cwd will be dirname(fullname), and fullname will be
    # absolute, i.e. /foo/bar, and the caller is expected to handle
    # restoring the metadata if hardlinking isn't possible.

    # FIXME: we can probably replace the target_vfs_path with the
    # relevant vfs item
    
    # hardlinks tracks a list of (restore_path, vfs_path, meta)
    # triples for each path we've written for a given hardlink_target.
    # This allows us to handle the case where we restore a set of
    # hardlinks out of order (with respect to the original save
    # call(s)) -- i.e. when we don't restore the hardlink_target path
    # first.  This data also allows us to attempt to handle other
    # situations like hardlink sets that change on disk during a save,
    # or between index and save.

    target = item.meta.hardlink_target
    assert(target)
    assert(fullname.startswith('/'))
    target_versions = hardlinks.get(target)
    if target_versions:
        # Check every path in the set that we've written so far for a match.
        for prev_path, prev_item in target_versions:
            if hardlink_compatible(prev_path, prev_item, item, top):
                try:
                    os.link(top + prev_path, top + fullname)
                    return True
                except OSError as e:
                    if e.errno != errno.EXDEV:
                        raise
    else:
        target_versions = []
        hardlinks[target] = target_versions
    target_versions.append((fullname, item))
    return False

def write_file_content(repo, dest_path, vfs_file):
    with vfs2.fopen(repo, vfs_file) as inf:
        with open(dest_path, 'wb') as outf:
            for b in chunkyreader(inf):
                outf.write(b)

def write_file_content_sparsely(repo, dest_path, vfs_file):
    with vfs2.fopen(repo, vfs_file) as inf:
        outfd = os.open(dest_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            trailing_zeros = 0;
            for b in chunkyreader(inf):
                trailing_zeros = write_sparsely(outfd, b, 512, trailing_zeros)
            pos = os.lseek(outfd, trailing_zeros, os.SEEK_END)
            os.ftruncate(outfd, pos)
        finally:
            os.close(outfd)
            
def restore(repo, parent_path, name, item, top, sparse, numeric_ids, owner_map,
            exclude_rxs, verbosity, hardlinks):
    global total_restored
    mode = vfs2.item_mode(item)
    treeish = S_ISDIR(mode)
    fullname = parent_path + '/' + name
    # Match behavior of index --exclude-rx with respect to paths.
    if should_rx_exclude_path(fullname + ('/' if treeish else ''),
                              exclude_rxs):
        return

    if not treeish:
        # Do this now so we'll have meta.symlink_target for verbose output
        item = vfs2.augment_item_meta(repo, item, include_size=True)
        meta = item.meta
        assert(meta.mode == mode)

    if stat.S_ISDIR(mode):
        if verbosity >= 1:
            print('%s/' % fullname)
    elif stat.S_ISLNK(mode):
        assert(meta.symlink_target)
        if verbosity >= 2:
            print('%s@ -> %s' % (fullname, meta.symlink_target))
    else:
        if verbosity >= 2:
            print(fullname)

    orig_cwd = os.getcwd()
    try:
        if treeish:
            # Assumes contents() returns '.' with the full metadata first
            sub_items = vfs2.contents(repo, item, want_meta=True)
            dot, item = next(sub_items, None)
            assert(dot == '.')
            item = vfs2.augment_item_meta(repo, item, include_size=True)
            meta = item.meta
            meta.create_path(name)
            os.chdir(name)
            total_restored += 1
            if verbosity >= 0:
                qprogress('Restoring: %d\r' % total_restored)
            for sub_name, sub_item in sub_items:
                restore(repo, fullname, sub_name, sub_item, top, sparse,
                        numeric_ids, owner_map, exclude_rxs, verbosity,
                        hardlinks)
            os.chdir('..')
            apply_metadata(meta, name, numeric_ids, owner_map)
        else:
            created_hardlink = False
            if meta.hardlink_target:
                created_hardlink = hardlink_if_possible(fullname, item, top,
                                                        hardlinks)
            if not created_hardlink:
                meta.create_path(name)
                if stat.S_ISREG(meta.mode):
                    if sparse:
                        write_file_content_sparsely(repo, name, item)
                    else:
                        write_file_content(repo, name, item)
            total_restored += 1
            if verbosity >= 0:
                qprogress('Restoring: %d\r' % total_restored)
            if not created_hardlink:
                apply_metadata(meta, name, numeric_ids, owner_map)
    finally:
        os.chdir(orig_cwd)

def main():
    o = options.Options(optspec)
    opt, flags, extra = o.parse(sys.argv[1:])
    verbosity = opt.verbose if not opt.quiet else -1
    
    git.check_repo_or_die()

    if not extra:
        o.fatal('must specify at least one filename to restore')

    exclude_rxs = parse_rx_excludes(flags, o.fatal)

    owner_map = {}
    for map_type in ('user', 'group', 'uid', 'gid'):
        owner_map[map_type] = parse_owner_mappings(map_type, flags, o.fatal)

    if opt.outdir:
        mkdirp(opt.outdir)
        os.chdir(opt.outdir)

    repo = LocalRepo()
    top = os.getcwd()
    hardlinks = {}
    for path in extra:
        if not valid_restore_path(path):
            add_error("path %r doesn't include a branch and revision" % path)
            continue
        try:
            resolved = vfs2.lresolve(repo, path, want_meta=True)
        except vfs2.IOError as e:
            add_error(e)
            continue
        path_parent, path_name = os.path.split(path)
        leaf_name, leaf_item = resolved[-1]
        if not leaf_item:
            add_error('error: cannot access %r in %r'
                      % ('/'.join(name for name, item in resolved),
                         path))
            continue
        if not path_name or path_name == '.':
            # Source is /foo/what/ever/ or /foo/what/ever/. -- extract
            # what/ever/* to the current directory, and if name == '.'
            # (i.e. /foo/what/ever/.), then also restore what/ever's
            # metadata to the current directory.
            treeish = vfs2.item_mode(leaf_item)
            if not treeish:
                add_error('%r cannot be restored as a directory' % path)
            else:
                items = vfs2.contents(repo, leaf_item, want_meta=True)
                dot, leaf_item = next(items, None)
                assert(dot == '.')
                for sub_name, sub_item in items:
                    restore(repo, '', sub_name, sub_item, top,
                            opt.sparse, opt.numeric_ids, owner_map,
                            exclude_rxs, verbosity, hardlinks)
                if path_name == '.':
                    leaf_item = vfs2.augment_item_meta(repo, leaf_item,
                                                       include_size=True)
                    apply_metadata(leaf_item.meta, '.',
                                   opt.numeric_ids, owner_map)
        else:
            restore(repo, '', leaf_name, leaf_item, top,
                    opt.sparse, opt.numeric_ids, owner_map,
                    exclude_rxs, verbosity, hardlinks)

    if verbosity >= 0:
        progress('Restoring: %d, done.\n' % total_restored)
    die_if_errors()

wrap_main(main)
