#!/usr/bin/env python
import sys, stat, time, math
from bup import hashsplit, git, options, index, client, metadata, hlinkdb
from bup.helpers import *
from bup.hashsplit import GIT_MODE_TREE, GIT_MODE_FILE, GIT_MODE_SYMLINK


optspec = """
bup save [-tc] [-n name] <filenames...>
--
r,remote=  hostname:/path/to/repo of remote repository
t,tree     output a tree id
c,commit   output a commit id
n,name=    name of backup set to update (if any)
d,date=    date for the commit (seconds since the epoch)
v,verbose  increase log output (can be used more than once)
q,quiet    don't show progress meter
smaller=   only back up files smaller than n bytes
bwlimit=   maximum bytes/sec to transmit to server
f,indexfile=  the name of the index file (normally BUP_DIR/bupindex)
strip      strips the path to every filename given
strip-path= path-prefix to be stripped when saving
graft=     a graft point *old_path*=*new_path* (can be used more than once)
#,compress=  set compression level to # (0-9, 9 is highest) [1]
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()
if not (opt.tree or opt.commit or opt.name):
    o.fatal("use one or more of -t, -c, -n")
if not extra:
    o.fatal("no filenames given")

opt.progress = (istty2 and not opt.quiet)
opt.smaller = parse_num(opt.smaller or 0)
if opt.bwlimit:
    client.bwlimit = parse_num(opt.bwlimit)

if opt.date:
    date = parse_date_or_fatal(opt.date, o.fatal)
else:
    date = time.time()

if opt.strip and opt.strip_path:
    o.fatal("--strip is incompatible with --strip-path")

graft_points = []
if opt.graft:
    if opt.strip:
        o.fatal("--strip is incompatible with --graft")

    if opt.strip_path:
        o.fatal("--strip-path is incompatible with --graft")

    for (option, parameter) in flags:
        if option == "--graft":
            splitted_parameter = parameter.split('=')
            if len(splitted_parameter) != 2:
                o.fatal("a graft point must be of the form old_path=new_path")
            old_path, new_path = splitted_parameter
            if not (old_path and new_path):
                o.fatal("a graft point cannot be empty")
            graft_points.append((realpath(old_path), realpath(new_path)))

is_reverse = os.environ.get('BUP_SERVER_REVERSE')
if is_reverse and opt.remote:
    o.fatal("don't use -r in reverse mode; it's automatic")

if opt.name and opt.name.startswith('.'):
    o.fatal("'%s' is not a valid branch name" % opt.name)
refname = opt.name and 'refs/heads/%s' % opt.name or None
if opt.remote or is_reverse:
    cli = client.Client(opt.remote)
    oldref = refname and cli.read_ref(refname) or None
    w = cli.new_packwriter()
else:
    cli = None
    oldref = refname and git.read_ref(refname) or None
    w = git.PackWriter(compression_level=opt.compress)

handle_ctrl_c()


def eatslash(dir):
    if dir.endswith('/'):
        return dir[:-1]
    else:
        return dir


# Metadata is stored in a file named .bupm in each directory.  The
# first metadata entry will be the metadata for the current directory.
# The remaining entries will be for each of the other directory
# elements, in the order they're listed in the index.
#
# Since the git tree elements are sorted according to
# git.shalist_item_sort_key, the metalist items are accumulated as
# (sort_key, metadata) tuples, and then sorted when the .bupm file is
# created.  The sort_key must be computed using the element's real
# name and mode rather than the git mode and (possibly mangled) name.

# Maintain a stack of information representing the current location in
# the archive being constructed.  The current path is recorded in
# parts, which will be something like ['', 'home', 'someuser'], and
# the accumulated content and metadata for of the dirs in parts is
# stored in parallel stacks in shalists and metalists.

parts = [] # Current archive position (stack of dir names).
shalists = [] # Hashes for each dir in paths.
metalists = [] # Metadata for each dir in paths.


def _push(part, metadata):
    # Enter a new archive directory -- make it the current directory.
    parts.append(part)
    shalists.append([])
    metalists.append([('', metadata)]) # This dir's metadata (no name).


def _pop(force_tree, dir_metadata=None):
    # Leave the current archive directory and add its tree to its parent.
    assert(len(parts) >= 1)
    part = parts.pop()
    shalist = shalists.pop()
    metalist = metalists.pop()
    if metalist and not force_tree:
        if dir_metadata: # Override the original metadata pushed for this dir.
            metalist = [('', dir_metadata)] + metalist[1:]
        sorted_metalist = sorted(metalist, key = lambda x : x[0])
        metadata = ''.join([m[1].encode() for m in sorted_metalist])
        shalist.append((0100644, '.bupm', w.new_blob(metadata)))
    tree = force_tree or w.new_tree(shalist)
    if shalists:
        shalists[-1].append((GIT_MODE_TREE,
                             git.mangle_name(part,
                                             GIT_MODE_TREE, GIT_MODE_TREE),
                             tree))
    return tree


lastremain = None
def progress_report(n):
    global count, subcount, lastremain
    subcount += n
    cc = count + subcount
    pct = total and (cc*100.0/total) or 0
    now = time.time()
    elapsed = now - tstart
    kps = elapsed and int(cc/1024./elapsed)
    kps_frac = 10 ** int(math.log(kps+1, 10) - 1)
    kps = int(kps/kps_frac)*kps_frac
    if cc:
        remain = elapsed*1.0/cc * (total-cc)
    else:
        remain = 0.0
    if (lastremain and (remain > lastremain)
          and ((remain - lastremain)/lastremain < 0.05)):
        remain = lastremain
    else:
        lastremain = remain
    hours = int(remain/60/60)
    mins = int(remain/60 - hours*60)
    secs = int(remain - hours*60*60 - mins*60)
    if elapsed < 30:
        remainstr = ''
        kpsstr = ''
    else:
        kpsstr = '%dk/s' % kps
        if hours:
            remainstr = '%dh%dm' % (hours, mins)
        elif mins:
            remainstr = '%dm%d' % (mins, secs)
        else:
            remainstr = '%ds' % secs
    qprogress('Saving: %.2f%% (%d/%dk, %d/%d files) %s %s\r'
              % (pct, cc/1024, total/1024, fcount, ftotal,
                 remainstr, kpsstr))


indexfile = opt.indexfile or git.repo('bupindex')
r = index.Reader(indexfile)
if not os.access(indexfile + '.meta', os.W_OK|os.R_OK):
    log('error: cannot access "%s"; have you run bup index?' % indexfile)
    sys.exit(1)
msr = index.MetaStoreReader(indexfile + '.meta')
hlink_db = hlinkdb.HLinkDB(indexfile + '.hlink')

def already_saved(ent):
    return ent.is_valid() and w.exists(ent.sha) and ent.sha

def wantrecurse_pre(ent):
    return not already_saved(ent)

def wantrecurse_during(ent):
    return not already_saved(ent) or ent.sha_missing()

def find_hardlink_target(hlink_db, ent):
    if hlink_db and not stat.S_ISDIR(ent.mode) and ent.nlink > 1:
        link_paths = hlink_db.node_paths(ent.dev, ent.ino)
        if link_paths:
            return link_paths[0]

total = ftotal = 0
if opt.progress:
    for (transname,ent) in r.filter(extra, wantrecurse=wantrecurse_pre):
        if not (ftotal % 10024):
            qprogress('Reading index: %d\r' % ftotal)
        exists = ent.exists()
        hashvalid = already_saved(ent)
        ent.set_sha_missing(not hashvalid)
        if not opt.smaller or ent.size < opt.smaller:
            if exists and not hashvalid:
                total += ent.size
        ftotal += 1
    progress('Reading index: %d, done.\n' % ftotal)
    hashsplit.progress_callback = progress_report

# Root collisions occur when strip or graft options map more than one
# path to the same directory (paths which originally had separate
# parents).  When that situation is detected, use empty metadata for
# the parent.  Otherwise, use the metadata for the common parent.
# Collision example: "bup save ... --strip /foo /foo/bar /bar".

# FIXME: Add collision tests, or handle collisions some other way.

# FIXME: Detect/handle strip/graft name collisions (other than root),
# i.e. if '/foo/bar' and '/bar' both map to '/'.

first_root = None
root_collision = None
tstart = time.time()
count = subcount = fcount = 0
lastskip_name = None
lastdir = ''
for (transname,ent) in r.filter(extra, wantrecurse=wantrecurse_during):
    (dir, file) = os.path.split(ent.name)
    exists = (ent.flags & index.IX_EXISTS)
    hashvalid = already_saved(ent)
    wasmissing = ent.sha_missing()
    oldsize = ent.size
    if opt.verbose:
        if not exists:
            status = 'D'
        elif not hashvalid:
            if ent.sha == index.EMPTY_SHA:
                status = 'A'
            else:
                status = 'M'
        else:
            status = ' '
        if opt.verbose >= 2:
            log('%s %-70s\n' % (status, ent.name))
        elif not stat.S_ISDIR(ent.mode) and lastdir != dir:
            if not lastdir.startswith(dir):
                log('%s %-70s\n' % (status, os.path.join(dir, '')))
            lastdir = dir

    if opt.progress:
        progress_report(0)
    fcount += 1
    
    if not exists:
        continue
    if opt.smaller and ent.size >= opt.smaller:
        if exists and not hashvalid:
            add_error('skipping large file "%s"' % ent.name)
            lastskip_name = ent.name
        continue

    assert(dir.startswith('/'))
    if opt.strip:
        dirp = stripped_path_components(dir, extra)
    elif opt.strip_path:
        dirp = stripped_path_components(dir, [opt.strip_path])
    elif graft_points:
        dirp = grafted_path_components(graft_points, dir)
    else:
        dirp = path_components(dir)

    # At this point, dirp contains a representation of the archive
    # path that looks like [(archive_dir_name, real_fs_path), ...].
    # So given "bup save ... --strip /foo/bar /foo/bar/baz", dirp
    # might look like this at some point:
    #   [('', '/foo/bar'), ('baz', '/foo/bar/baz'), ...].

    # This dual representation supports stripping/grafting, where the
    # archive path may not have a direct correspondence with the
    # filesystem.  The root directory is represented by an initial
    # component named '', and any component that doesn't have a
    # corresponding filesystem directory (due to grafting, for
    # example) will have a real_fs_path of None, i.e. [('', None),
    # ...].

    if first_root == None:
        dir_name, fs_path = dirp[0]
        first_root = dirp[0]
        # Not indexed, so just grab the FS metadata or use empty metadata.
        try:
           meta = metadata.from_path(fs_path) if fs_path else metadata.Metadata()
        except (OSError, IOError), e:
            add_error(e)
            lastskip_name = dir_name
        else:
           _push(dir_name, meta)
    elif first_root != dirp[0]:
        root_collision = True

    # If switching to a new sub-tree, finish the current sub-tree.
    while parts > [x[0] for x in dirp]:
        _pop(force_tree = None)

    # If switching to a new sub-tree, start a new sub-tree.
    for path_component in dirp[len(parts):]:
        dir_name, fs_path = path_component
        # Not indexed, so just grab the FS metadata or use empty metadata.
        try:
           meta = metadata.from_path(fs_path) if fs_path else metadata.Metadata()
        except (OSError, IOError), e:
            add_error(e)
            lastskip_name = dir_name
        else:
           _push(dir_name, meta)

    if not file:
        if len(parts) == 1:
            continue # We're at the top level -- keep the current root dir
        # Since there's no filename, this is a subdir -- finish it.
        oldtree = already_saved(ent) # may be None
        newtree = _pop(force_tree = oldtree)
        if not oldtree:
            if lastskip_name and lastskip_name.startswith(ent.name):
                ent.invalidate()
            else:
                ent.validate(GIT_MODE_TREE, newtree)
            ent.repack()
        if exists and wasmissing:
            count += oldsize
        continue

    # it's not a directory
    id = None
    if hashvalid:
        id = ent.sha
        git_name = git.mangle_name(file, ent.mode, ent.gitmode)
        git_info = (ent.gitmode, git_name, id)
        shalists[-1].append(git_info)
        sort_key = git.shalist_item_sort_key((ent.mode, file, id))
        meta = msr.metadata_at(ent.meta_ofs)
        meta.hardlink_target = find_hardlink_target(hlink_db, ent)
        # Restore the times that were cleared to 0 in the metastore.
        (meta.atime, meta.mtime, meta.ctime) = (ent.atime, ent.mtime, ent.ctime)
        metalists[-1].append((sort_key, meta))
    else:
        if stat.S_ISREG(ent.mode):
            try:
                f = hashsplit.open_noatime(ent.name)
            except (IOError, OSError), e:
                add_error(e)
                lastskip_name = ent.name
            else:
                try:
                    (mode, id) = hashsplit.split_to_blob_or_tree(
                                            w.new_blob, w.new_tree, [f],
                                            keep_boundaries=False)
                except (IOError, OSError), e:
                    add_error('%s: %s' % (ent.name, e))
                    lastskip_name = ent.name
        else:
            if stat.S_ISDIR(ent.mode):
                assert(0)  # handled above
            elif stat.S_ISLNK(ent.mode):
                try:
                    rl = os.readlink(ent.name)
                except (OSError, IOError), e:
                    add_error(e)
                    lastskip_name = ent.name
                else:
                    (mode, id) = (GIT_MODE_SYMLINK, w.new_blob(rl))
            else:
                # Everything else should be fully described by its
                # metadata, so just record an empty blob, so the paths
                # in the tree and .bupm will match up.
                (mode, id) = (GIT_MODE_FILE, w.new_blob(""))

        if id:
            ent.validate(mode, id)
            ent.repack()
            git_name = git.mangle_name(file, ent.mode, ent.gitmode)
            git_info = (mode, git_name, id)
            shalists[-1].append(git_info)
            sort_key = git.shalist_item_sort_key((ent.mode, file, id))
            hlink = find_hardlink_target(hlink_db, ent)
            try:
                meta = metadata.from_path(ent.name, hardlink_target=hlink)
            except (OSError, IOError), e:
                add_error(e)
                lastskip_name = ent.name
            else:
                metalists[-1].append((sort_key, meta))

    if exists and wasmissing:
        count += oldsize
        subcount = 0


if opt.progress:
    pct = total and count*100.0/total or 100
    progress('Saving: %.2f%% (%d/%dk, %d/%d files), done.    \n'
             % (pct, count/1024, total/1024, fcount, ftotal))

while len(parts) > 1: # _pop() all the parts above the root
    _pop(force_tree = None)
assert(len(shalists) == 1)
assert(len(metalists) == 1)

# Finish the root directory.
tree = _pop(force_tree = None,
            # When there's a collision, use empty metadata for the root.
            dir_metadata = metadata.Metadata() if root_collision else None)

if opt.tree:
    print tree.encode('hex')
if opt.commit or opt.name:
    msg = 'bup save\n\nGenerated by command:\n%r' % sys.argv
    commit = w.new_commit(oldref, tree, date, msg)
    if opt.commit:
        print commit.encode('hex')

msr.close()
w.close()  # must close before we can update the ref
        
if opt.name:
    if cli:
        cli.update_ref(refname, commit, oldref)
    else:
        git.update_ref(refname, commit, oldref)

if cli:
    cli.close()

if saved_errors:
    log('WARNING: %d errors encountered while saving.\n' % len(saved_errors))
    sys.exit(1)
