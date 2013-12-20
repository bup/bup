#!/usr/bin/env python
import copy, errno, sys, stat, re
from bup import options, git, metadata, vfs
from bup.helpers import *

optspec = """
bup restore [-C outdir] </branch/revision/path/to/dir ...>
--
C,outdir=   change to given outdir before extracting files
numeric-ids restore numeric IDs (user, group, etc.) rather than names
exclude-rx= skip paths matching the unanchored regex (may be repeated)
exclude-rx-from= skip --exclude-rx patterns in file (may be repeated)
v,verbose   increase log output (can be used more than once)
map-user=   given OLD=NEW, restore OLD user as NEW user
map-group=  given OLD=NEW, restore OLD group as NEW group
map-uid=    given OLD=NEW, restore OLD uid as NEW uid
map-gid=    given OLD=NEW, restore OLD gid as NEW gid
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


def valid_restore_path(path):
    path = os.path.normpath(path)
    if path.startswith('/'):
        path = path[1:]
    if '/' in path:
        return True


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


# Track a list of (restore_path, vfs_path, meta) triples for each path
# we've written for a given hardlink_target.  This allows us to handle
# the case where we restore a set of hardlinks out of order (with
# respect to the original save call(s)) -- i.e. when we don't restore
# the hardlink_target path first.  This data also allows us to attempt
# to handle other situations like hardlink sets that change on disk
# during a save, or between index and save.
targets_written = {}

def hardlink_compatible(target_path, target_vfs_path, target_meta,
                        src_node, src_meta):
    global top
    if not os.path.exists(target_path):
        return False
    target_node = top.lresolve(target_vfs_path)
    if src_node.mode != target_node.mode \
            or src_node.mtime != target_node.mtime \
            or src_node.ctime != target_node.ctime \
            or src_node.hash != target_node.hash:
        return False
    if not src_meta.same_file(target_meta):
        return False
    return True


def hardlink_if_possible(fullname, node, meta):
    """Find a suitable hardlink target, link to it, and return true,
    otherwise return false."""
    # Expect the caller to handle restoring the metadata if
    # hardlinking isn't possible.
    global targets_written
    target = meta.hardlink_target
    target_versions = targets_written.get(target)
    if target_versions:
        # Check every path in the set that we've written so far for a match.
        for (target_path, target_vfs_path, target_meta) in target_versions:
            if hardlink_compatible(target_path, target_vfs_path, target_meta,
                                   node, meta):
                try:
                    os.link(target_path, fullname)
                    return True
                except OSError, e:
                    if e.errno != errno.EXDEV:
                        raise
    else:
        target_versions = []
        targets_written[target] = target_versions
    full_vfs_path = node.fullname()
    target_versions.append((fullname, full_vfs_path, meta))
    return False


def write_file_content(fullname, n):
    outf = open(fullname, 'wb')
    try:
        for b in chunkyreader(n.open()):
            outf.write(b)
    finally:
        outf.close()


def find_dir_item_metadata_by_name(dir, name):
    """Find metadata in dir (a node) for an item with the given name,
    or for the directory itself if the name is ''."""
    meta_stream = None
    try:
        mfile = dir.metadata_file() # VFS file -- cannot close().
        if mfile:
            meta_stream = mfile.open()
            # First entry is for the dir itself.
            meta = metadata.Metadata.read(meta_stream)
            if name == '':
                return meta
            for sub in dir:
                if stat.S_ISDIR(sub.mode):
                    meta = find_dir_item_metadata_by_name(sub, '')
                else:
                    meta = metadata.Metadata.read(meta_stream)
                if sub.name == name:
                    return meta
    finally:
        if meta_stream:
            meta_stream.close()


def do_root(n, owner_map, restore_root_meta = True):
    # Very similar to do_node(), except that this function doesn't
    # create a path for n's destination directory (and so ignores
    # n.fullname).  It assumes the destination is '.', and restores
    # n's metadata and content there.
    global total_restored, opt
    meta_stream = None
    try:
        # Directory metadata is the first entry in any .bupm file in
        # the directory.  Get it.
        mfile = n.metadata_file() # VFS file -- cannot close().
        if mfile:
            meta_stream = mfile.open()
            root_meta = metadata.Metadata.read(meta_stream)
        print_info(n, '.')
        total_restored += 1
        plog('Restoring: %d\r' % total_restored)
        for sub in n:
            m = None
            # Don't get metadata if this is a dir -- handled in sub do_node().
            if meta_stream and not stat.S_ISDIR(sub.mode):
                m = metadata.Metadata.read(meta_stream)
            do_node(n, sub, owner_map, meta = m)
        if root_meta and restore_root_meta:
            apply_metadata(root_meta, '.', opt.numeric_ids, owner_map)
    finally:
        if meta_stream:
            meta_stream.close()


def do_node(top, n, owner_map, meta = None):
    # Create n.fullname(), relative to the current directory, and
    # restore all of its metadata, when available.  The meta argument
    # will be None for dirs, or when there is no .bupm (i.e. no
    # metadata).
    global total_restored, opt
    meta_stream = None
    try:
        fullname = n.fullname(stop_at=top)
        # Match behavior of index --exclude-rx with respect to paths.
        exclude_candidate = '/' + fullname
        if(stat.S_ISDIR(n.mode)):
            exclude_candidate += '/'
        if should_rx_exclude_path(exclude_candidate, exclude_rxs):
            return
        # If this is a directory, its metadata is the first entry in
        # any .bupm file inside the directory.  Get it.
        if(stat.S_ISDIR(n.mode)):
            mfile = n.metadata_file() # VFS file -- cannot close().
            if mfile:
                meta_stream = mfile.open()
                meta = metadata.Metadata.read(meta_stream)
        print_info(n, fullname)

        created_hardlink = False
        if meta and meta.hardlink_target:
            created_hardlink = hardlink_if_possible(fullname, n, meta)

        if not created_hardlink:
            create_path(n, fullname, meta)
            if meta:
                if stat.S_ISREG(meta.mode):
                    write_file_content(fullname, n)
            elif stat.S_ISREG(n.mode):
                write_file_content(fullname, n)

        total_restored += 1
        plog('Restoring: %d\r' % total_restored)
        for sub in n:
            m = None
            # Don't get metadata if this is a dir -- handled in sub do_node().
            if meta_stream and not stat.S_ISDIR(sub.mode):
                m = metadata.Metadata.read(meta_stream)
            do_node(top, sub, owner_map, meta = m)
        if meta and not created_hardlink:
            apply_metadata(meta, fullname, opt.numeric_ids, owner_map)
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
    
exclude_rxs = parse_rx_excludes(flags, o.fatal)

owner_map = {}
for map_type in ('user', 'group', 'uid', 'gid'):
    owner_map[map_type] = parse_owner_mappings(map_type, flags, o.fatal)

if opt.outdir:
    mkdirp(opt.outdir)
    os.chdir(opt.outdir)

ret = 0
for d in extra:
    if not valid_restore_path(d):
        add_error("ERROR: path %r doesn't include a branch and revision" % d)
        continue
    path,name = os.path.split(d)
    try:
        n = top.lresolve(d)
    except vfs.NodeError, e:
        add_error(e)
        continue
    isdir = stat.S_ISDIR(n.mode)
    if not name or name == '.':
        # Source is /foo/what/ever/ or /foo/what/ever/. -- extract
        # what/ever/* to the current directory, and if name == '.'
        # (i.e. /foo/what/ever/.), then also restore what/ever's
        # metadata to the current directory.
        if not isdir:
            add_error('%r: not a directory' % d)
        else:
            do_root(n, owner_map, restore_root_meta = (name == '.'))
    else:
        # Source is /foo/what/ever -- extract ./ever to cwd.
        if isinstance(n, vfs.FakeSymlink):
            # Source is actually /foo/what, i.e. a top-level commit
            # like /foo/latest, which is a symlink to ../.commit/SHA.
            # So dereference it, and restore ../.commit/SHA/. to
            # "./what/.".
            target = n.dereference()
            mkdirp(n.name)
            os.chdir(n.name)
            do_root(target, owner_map)
        else: # Not a directory or fake symlink.
            meta = find_dir_item_metadata_by_name(n.parent, n.name)
            do_node(n.parent, n, owner_map, meta = meta)

if not opt.quiet:
    progress('Restoring: %d, done.\n' % total_restored)

if saved_errors:
    log('WARNING: %d errors encountered while restoring.\n' % len(saved_errors))
    sys.exit(1)
