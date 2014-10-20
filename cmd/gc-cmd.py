#!/usr/bin/env python
import glob, os, stat, subprocess, sys, tempfile
from bup import bloom, git, midx, options, vfs
from bup.git import walk_object
from bup.helpers import handle_ctrl_c, log, progress, qprogress, saved_errors
from os.path import basename

# This command uses a Bloom filter to track the live objects during
# the mark phase.  This means that the collection is probabilistic; it
# may retain some (known) percentage of garbage, but it can also work
# within a reasonable, fixed RAM budget for any particular percentage
# and repository size.
#
# The collection proceeds as follows:
#
#   - Scan all live objects by walking all of the refs, and insert
#     every hash encountered into a new Bloom "liveness" filter.
#     Compute the size of the liveness filter based on the total
#     number of objects in the repository.  This is the "mark phase".
#
#   - Clear the data that's dependent on the repository's object set,
#     i.e. the reflog, the normal Bloom filter, and the midxes.
#
#   - Traverse all of the pack files, consulting the liveness filter
#     to decide which objects to keep.
#
#     For each pack file, rewrite it iff it probably contains more
#     than (currently) 10% garbage (computed by an initial traversal
#     of the packfile in consultation with the liveness filter).  To
#     rewrite, traverse the packfile (again) and write each hash that
#     tests positive against the liveness filter to a packwriter.
#
#     During the traversal of all of the packfiles, delete redundant,
#     old packfiles only after the packwriter has finished the pack
#     that contains all of their live objects.
#
# The current code unconditionally tracks the set of tree hashes seen
# during the mark phase, and skips any that have already been visited.
# This should decrease the IO load at the cost of increased RAM use.

# FIXME: add a bloom filter tuning parameter?


optspec = """
bup gc [options...]
--
v,verbose   increase log output (can be used more than once)
threshold   only rewrite a packfile if it's over this percent garbage [10]
#,compress= set compression level to # (0-9, 9 is highest) [1]
unsafe      use the command even though it may be DANGEROUS
"""


class Nonlocal:
    pass


def count_objects(dir):
    # For now we'll just use open_idx(), but we could probably be much
    # more efficient since all we need is a single integer (the last
    # fanout entry) from each index.
    global opt
    object_count = 0
    indexes = glob.glob(os.path.join(dir, '*.idx'))
    for i, idx_name in enumerate(indexes):
        if opt.verbose:
            log('found %d objects (%d/%d %s)\r'
                % (object_count, i + 1, len(indexes),
                   os.path.basename(idx_name)))
        idx = git.open_idx(idx_name)
        object_count += len(idx)
    return object_count


def report_live_item(n, total, ref_name, ref_id, item):
    global opt
    status = 'scanned %02.2f%%' % (n * 100.0 / total)
    hex_id = ref_id.encode('hex')
    dirslash = '/' if item.type == 'tree' else ''
    chunk_path = item.chunk_path

    if chunk_path:
        if opt.verbose < 4:
            return
        ps = '/'.join(item.path)
        chunk_ps = '/'.join(chunk_path)
        log('%s %s:%s/%s%s\n' % (status, hex_id, ps, chunk_ps, dirslash))
        return

    # Top commit, for example has none.
    demangled = git.demangle_name(item.path[-1], item.mode)[0] if item.path \
                else None

    # Don't print mangled paths unless the verbosity is over 3.
    if demangled:
        ps = '/'.join(item.path[:-1] + [demangled])
        if opt.verbose == 1:
            qprogress('%s %s:%s%s\r' % (status, hex_id, ps, dirslash))
        elif (opt.verbose > 1 and item.type == 'tree') \
             or (opt.verbose > 2 and item.type == 'blob'):
            log('%s %s:%s%s\n' % (status, hex_id, ps, dirslash))
    elif opt.verbose > 3:
        ps = '/'.join(item.path)
        log('%s %s:%s%s\n' % (status, hex_id, ps, dirslash))


def find_live_objects(existing_count, cat_pipe, opt):
    prune_visited_trees = True # In case we want a command line option later
    pack_dir = git.repo('objects/pack')
    ffd, bloom_filename = tempfile.mkstemp('.bloom', 'tmp-gc-', pack_dir)
    os.close(ffd)
    # FIXME: allow selection of k?
    # FIXME: support ephemeral bloom filters (i.e. *never* written to disk)
    live_objs = bloom.create(bloom_filename, expected=existing_count, k=None)
    stop_at, trees_visited = None, None
    if prune_visited_trees:
        trees_visited = set()
        stop_at = lambda (x): x.decode('hex') in trees_visited
    approx_live_count = 0
    for ref_name, ref_id in git.list_refs():
        for item in walk_object(cat_pipe, ref_id.encode('hex'),
                                stop_at=stop_at,
                                include_data=None):
            # FIXME: batch ids
            if opt.verbose:
                report_live_item(approx_live_count, existing_count,
                                 ref_name, ref_id, item)
            bin_id = item.id.decode('hex')
            if trees_visited is not None and item.type == 'tree':
                trees_visited.add(bin_id)
            if opt.verbose:
                if not live_objs.exists(bin_id):
                    live_objs.add(bin_id)
                    approx_live_count += 1
            else:
                live_objs.add(bin_id)
    trees_visited = None
    if opt.verbose:
        log('expecting to retain about %.2f%% unnecessary objects\n'
            % live_objs.pfalse_positive())
    return live_objs


def sweep(live_objects, existing_count, cat_pipe, opt):
    # Traverse all the packs, saving the (probably) live data.

    ns = Nonlocal()
    ns.stale_files = []
    def remove_stale_files(new_pack_prefix):
        if opt.verbose and new_pack_prefix:
            log('created ' + basename(new_pack_prefix) + '\n')
        for p in ns.stale_files:
            if opt.verbose:
                log('removing ' + basename(p) + '\n')
            os.unlink(p)
        ns.stale_files = []

    writer = git.PackWriter(objcache_maker=None,
                            compression_level=opt.compress,
                            run_midx=False,
                            on_pack_finish=remove_stale_files)

    # FIXME: sanity check .idx names vs .pack names?
    collect_count = 0
    for idx_name in glob.glob(os.path.join(git.repo('objects/pack'), '*.idx')):
        if opt.verbose:
            qprogress('preserving live data (%d%% complete)\r'
                      % ((float(collect_count) / existing_count) * 100))
        idx = git.open_idx(idx_name)

        idx_live_count = 0
        for i in xrange(0, len(idx)):
            sha = idx.shatable[i * 20 : (i + 1) * 20]
            if live_objects.exists(sha):
                idx_live_count += 1

        collect_count += idx_live_count
        if idx_live_count == 0:
            if opt.verbose:
                log('deleting %s\n'
                    % git.repo_rel(basename(idx_name)))
            ns.stale_files.append(idx_name)
            ns.stale_files.append(idx_name[:-3] + 'pack')
            continue

        live_frac = idx_live_count / float(len(idx))
        if live_frac > ((100 - opt.threshold) / 100.0):
            if opt.verbose:
                log('keeping %s (%d%% live)\n' % (git.repo_rel(basename(idx_name)),
                                                  live_frac * 100))
            continue

        if opt.verbose:
            log('rewriting %s (%.2f%% live)\n' % (basename(idx_name),
                                                  live_frac * 100))
        for i in xrange(0, len(idx)):
            sha = idx.shatable[i * 20 : (i + 1) * 20]
            if live_objects.exists(sha):
                item_it = cat_pipe.get(sha.encode('hex'))
                type = item_it.next()
                writer.write(sha, type, ''.join(item_it))

        ns.stale_files.append(idx_name)
        ns.stale_files.append(idx_name[:-3] + 'pack')

    if opt.verbose:
        progress('preserving live data (%d%% complete)\n'
                 % ((float(collect_count) / existing_count) * 100))

    # Nothing should have recreated midx/bloom yet.
    pack_dir = git.repo('objects/pack')
    assert(not os.path.exists(os.path.join(pack_dir, 'bup.bloom')))
    assert(not glob.glob(os.path.join(pack_dir, '*.midx')))

    # try/catch should call writer.abort()?
    # This will finally run midx.
    writer.close()  # Can only change refs (if needed) after this.
    remove_stale_files(None)  # In case we didn't write to the writer.

    if opt.verbose:
        log('discarded %d%% of objects\n'
            % ((existing_count - count_objects(pack_dir))
               / float(existing_count) * 100))


# FIXME: server mode?
# FIXME: make sure client handles server-side changes reasonably

handle_ctrl_c()

o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if not opt.unsafe:
    o.fatal('refusing to run dangerous, experimental command without --unsafe')

if extra:
    o.fatal('no positional parameters expected')

if opt.threshold:
    try:
        opt.threshold = int(opt.threshold)
    except ValueError:
        o.fatal('threshold must be an integer percentage value')
    if opt.threshold < 0 or opt.threshold > 100:
        o.fatal('threshold must be an integer percentage value')

git.check_repo_or_die()

cat_pipe = vfs.cp()
existing_count = count_objects(git.repo('objects/pack'))
if opt.verbose:
    log('found %d objects\n' % existing_count)
if not existing_count:
    if opt.verbose:
        log('nothing to collect\n')
else:
    live_objects = find_live_objects(existing_count, cat_pipe, opt)
    try:
        # FIXME: just rename midxes and bloom, and restore them at the end if
        # we didn't change any packs?
        if opt.verbose: log('clearing midx files\n')
        midx.clear_midxes()
        if opt.verbose: log('clearing bloom filter\n')
        bloom.clear_bloom(git.repo('objects/pack'))
        if opt.verbose: log('clearing reflog\n')
        expirelog_cmd = ['git', 'reflog', 'expire', '--all', '--expire=all']
        expirelog = subprocess.Popen(expirelog_cmd, preexec_fn = git._gitenv())
        git._git_wait(' '.join(expirelog_cmd), expirelog)
        if opt.verbose: log('removing unreachable data\n')
        sweep(live_objects, existing_count, cat_pipe, opt)
    finally:
        live_objects.close()
        os.unlink(live_objects.name)

if saved_errors:
    log('WARNING: %d errors encountered during gc\n' % len(saved_errors))
    sys.exit(1)
