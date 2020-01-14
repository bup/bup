
from __future__ import absolute_import
from binascii import hexlify, unhexlify
from os.path import basename
import glob, os, subprocess, sys, tempfile

from bup import bloom, git, midx
from bup.compat import hexstr, range
from bup.git import MissingObject, walk_object
from bup.helpers import Nonlocal, log, progress, qprogress
from bup.io import path_msg

# This garbage collector uses a Bloom filter to track the live objects
# during the mark phase.  This means that the collection is
# probabilistic; it may retain some (known) percentage of garbage, but
# it can also work within a reasonable, fixed RAM budget for any
# particular percentage and repository size.
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


def count_objects(dir, verbosity):
    # For now we'll just use open_idx(), but we could probably be much
    # more efficient since all we need is a single integer (the last
    # fanout entry) from each index.
    object_count = 0
    indexes = glob.glob(os.path.join(dir, b'*.idx'))
    for i, idx_name in enumerate(indexes):
        if verbosity:
            log('found %d objects (%d/%d %s)\r'
                % (object_count, i + 1, len(indexes),
                   path_msg(basename(idx_name))))
        idx = git.open_idx(idx_name)
        object_count += len(idx)
    return object_count


def report_live_item(n, total, ref_name, ref_id, item, verbosity):
    status = 'scanned %02.2f%%' % (n * 100.0 / total)
    hex_id = hexstr(ref_id)
    dirslash = b'/' if item.type == b'tree' else b''
    chunk_path = item.chunk_path

    if chunk_path:
        if verbosity < 4:
            return
        ps = b'/'.join(item.path)
        chunk_ps = b'/'.join(chunk_path)
        log('%s %s:%s/%s%s\n' % (status, hex_id, path_msg(ps),
                                 path_msg(chunk_ps), path_msg(dirslash)))
        return

    # Top commit, for example has none.
    demangled = git.demangle_name(item.path[-1], item.mode)[0] if item.path \
                else None

    # Don't print mangled paths unless the verbosity is over 3.
    if demangled:
        ps = b'/'.join(item.path[:-1] + [demangled])
        if verbosity == 1:
            qprogress('%s %s:%s%s\r' % (status, hex_id, path_msg(ps),
                                        path_msg(dirslash)))
        elif (verbosity > 1 and item.type == b'tree') \
             or (verbosity > 2 and item.type == b'blob'):
            log('%s %s:%s%s\n' % (status, hex_id, path_msg(ps),
                                  path_msg(dirslash)))
    elif verbosity > 3:
        ps = b'/'.join(item.path)
        log('%s %s:%s%s\n' % (status, hex_id, path_msg(ps), path_msg(dirslash)))


def find_live_objects(existing_count, cat_pipe, verbosity=0):
    prune_visited_trees = True # In case we want a command line option later
    pack_dir = git.repo(b'objects/pack')
    ffd, bloom_filename = tempfile.mkstemp(b'.bloom', b'tmp-gc-', pack_dir)
    os.close(ffd)
    # FIXME: allow selection of k?
    # FIXME: support ephemeral bloom filters (i.e. *never* written to disk)
    live_objs = bloom.create(bloom_filename, expected=existing_count, k=None)
    # live_objs will hold on to the fd until close or exit
    os.unlink(bloom_filename)
    stop_at, trees_visited = None, None
    if prune_visited_trees:
        trees_visited = set()
        stop_at = lambda x: unhexlify(x) in trees_visited
    approx_live_count = 0
    for ref_name, ref_id in git.list_refs():
        for item in walk_object(cat_pipe.get, hexlify(ref_id), stop_at=stop_at,
                                include_data=None):
            # FIXME: batch ids
            if verbosity:
                report_live_item(approx_live_count, existing_count,
                                 ref_name, ref_id, item, verbosity)
            if trees_visited is not None and item.type == b'tree':
                trees_visited.add(item.oid)
            if verbosity:
                if not live_objs.exists(item.oid):
                    live_objs.add(item.oid)
                    approx_live_count += 1
            else:
                live_objs.add(item.oid)
    trees_visited = None
    if verbosity:
        log('expecting to retain about %.2f%% unnecessary objects\n'
            % live_objs.pfalse_positive())
    return live_objs


def sweep(live_objects, existing_count, cat_pipe, threshold, compression,
          verbosity):
    # Traverse all the packs, saving the (probably) live data.

    ns = Nonlocal()
    ns.stale_files = []
    def remove_stale_files(new_pack_prefix):
        if verbosity and new_pack_prefix:
            log('created ' + path_msg(basename(new_pack_prefix)) + '\n')
        for p in ns.stale_files:
            if new_pack_prefix and p.startswith(new_pack_prefix):
                continue  # Don't remove the new pack file
            if verbosity:
                log('removing ' + path_msg(basename(p)) + '\n')
            os.unlink(p)
        if ns.stale_files:  # So git cat-pipe will close them
            cat_pipe.restart()
        ns.stale_files = []

    writer = git.PackWriter(objcache_maker=lambda : None,
                            compression_level=compression,
                            run_midx=False,
                            on_pack_finish=remove_stale_files)

    # FIXME: sanity check .idx names vs .pack names?
    collect_count = 0
    for idx_name in glob.glob(os.path.join(git.repo(b'objects/pack'), b'*.idx')):
        if verbosity:
            qprogress('preserving live data (%d%% complete)\r'
                      % ((float(collect_count) / existing_count) * 100))
        idx = git.open_idx(idx_name)

        idx_live_count = 0
        for sha in idx:
            if live_objects.exists(sha):
                idx_live_count += 1

        collect_count += idx_live_count
        if idx_live_count == 0:
            if verbosity:
                log('deleting %s\n'
                    % path_msg(git.repo_rel(basename(idx_name))))
            ns.stale_files.append(idx_name)
            ns.stale_files.append(idx_name[:-3] + b'pack')
            continue

        live_frac = idx_live_count / float(len(idx))
        if live_frac > ((100 - threshold) / 100.0):
            if verbosity:
                log('keeping %s (%d%% live)\n' % (git.repo_rel(basename(idx_name)),
                                                  live_frac * 100))
            continue

        if verbosity:
            log('rewriting %s (%.2f%% live)\n' % (basename(idx_name),
                                                  live_frac * 100))
        for sha in idx:
            if live_objects.exists(sha):
                item_it = cat_pipe.get(hexlify(sha))
                _, typ, _ = next(item_it)
                writer.just_write(sha, typ, b''.join(item_it))

        ns.stale_files.append(idx_name)
        ns.stale_files.append(idx_name[:-3] + b'pack')

    if verbosity:
        progress('preserving live data (%d%% complete)\n'
                 % ((float(collect_count) / existing_count) * 100))

    # Nothing should have recreated midx/bloom yet.
    pack_dir = git.repo(b'objects/pack')
    assert(not os.path.exists(os.path.join(pack_dir, b'bup.bloom')))
    assert(not glob.glob(os.path.join(pack_dir, b'*.midx')))

    # try/catch should call writer.abort()?
    # This will finally run midx.
    writer.close()  # Can only change refs (if needed) after this.
    remove_stale_files(None)  # In case we didn't write to the writer.

    if verbosity:
        log('discarded %d%% of objects\n'
            % ((existing_count - count_objects(pack_dir, verbosity))
               / float(existing_count) * 100))


def bup_gc(threshold=10, compression=1, verbosity=0):
    cat_pipe = git.cp()
    existing_count = count_objects(git.repo(b'objects/pack'), verbosity)
    if verbosity:
        log('found %d objects\n' % existing_count)
    if not existing_count:
        if verbosity:
            log('nothing to collect\n')
    else:
        try:
            live_objects = find_live_objects(existing_count, cat_pipe,
                                             verbosity=verbosity)
        except MissingObject as ex:
            log('bup: missing object %r \n' % hexstr(ex.oid))
            sys.exit(1)
        try:
            # FIXME: just rename midxes and bloom, and restore them at the end if
            # we didn't change any packs?
            packdir = git.repo(b'objects/pack')
            if verbosity: log('clearing midx files\n')
            midx.clear_midxes(packdir)
            if verbosity: log('clearing bloom filter\n')
            bloom.clear_bloom(packdir)
            if verbosity: log('clearing reflog\n')
            expirelog_cmd = [b'git', b'reflog', b'expire', b'--all', b'--expire=all']
            expirelog = subprocess.Popen(expirelog_cmd, env=git._gitenv())
            git._git_wait(b' '.join(expirelog_cmd), expirelog)
            if verbosity: log('removing unreachable data\n')
            sweep(live_objects, existing_count, cat_pipe,
                  threshold, compression,
                  verbosity)
        finally:
            live_objects.close()
