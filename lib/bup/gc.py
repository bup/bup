
from binascii import hexlify, unhexlify
from contextlib import ExitStack
from itertools import chain
from os.path import basename
import glob, os, re, subprocess, sys, tempfile

from bup import bloom, git, midx
from bup.compat import hexstr, pending_raise
from bup.git import MissingObject, walk_object
from bup.helpers import \
    EXIT_FAILURE, log, note_error, progress, qprogress, reprogress
from bup.io import path_msg
from bup.repo import LocalRepo

# This garbage collector uses a Bloom filter to track the live blobs
# during the mark phase.  This means that the collection is
# probabilistic; it may retain some (known) percentage of garbage, but
# it can also work within a reasonable, fixed RAM budget for any
# particular percentage and repository size.
#
# The collection proceeds as follows:
#
#   - Scan all live objects by walking all of the refs, and insert
#     every blob encountered into a new Bloom filter.  Compute the
#     size of the filter based on the total number of objects in the
#     repository.  Insert all other object hashes into a set.  This
#     set and the Bloom filter, taken together, are the "liveness
#     filter".  This is the "mark phase".
#
#   - Clear the data that's dependent on the repository's object
#     collection, i.e. the reflog, the normal Bloom filter, and the
#     midxes.
#
#   - Traverse all of the pack files, consulting the liveness filter
#     to decide which objects to keep.
#
#     For each pack file, rewrite it if it contains a tree or commit
#     that is now garbage, or if it probably contains more than
#     (currently) 10% garbage.  To rewrite, traverse the packfile
#     (again) and write each hash that tests positive against the
#     liveness filter to a packwriter.
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
            qprogress('found %d objects (%d/%d %s)\r'
                      % (object_count, i + 1, len(indexes),
                         path_msg(basename(idx_name))))
        with git.open_idx(idx_name) as idx:
            object_count += len(idx)
    return object_count


def report_missing(ref_name, item, verbosity):
    chunks = item.chunk_path
    if chunks:
        path = chain(item.path, chunks)
    else:
        # Top commit, for example has none.
        if item.path:
            demangled = git.demangle_name(item.path[-1], item.mode)[0]
            path = chain(item.path[:-1], [demangled])
        else:
            path = item.path
    ref = path_msg(ref_name)
    path = path_msg(b'/'.join(path))
    if item.type == b'tree':
        note_error(f'missing {ref}:{path}/\n')
    else:
        note_error(f'missing {ref}:{path}\n')


def report_live_item(n, total, ref_name, ref_id, item, verbosity):
    status = 'scanned %02.2f%%' % (n * 100.0 / total)
    dirslash = b'/' if item.type == b'tree' else b''
    chunk_path = item.chunk_path

    if chunk_path:
        if verbosity < 4:
            return
        ps = b'/'.join(item.path)
        chunk_ps = b'/'.join(chunk_path)
        log('%s %s:%s/%s%s\n' % (status, path_msg(ref_name), path_msg(ps),
                                 path_msg(chunk_ps), path_msg(dirslash)))
        return

    # Top commit, for example has none.
    demangled = git.demangle_name(item.path[-1], item.mode)[0] if item.path \
                else None

    # Don't print mangled paths unless the verbosity is over 3.
    if demangled:
        ps = b'/'.join(item.path[:-1] + [demangled])
        if verbosity == 1:
            qprogress('%s %s:%s%s\r' % (status, path_msg(ref_name), path_msg(ps),
                                        path_msg(dirslash)))
        elif (verbosity > 1 and item.type == b'tree') \
             or (verbosity > 2 and item.type == b'blob'):
            log('%s %s:%s%s\n' % (status, path_msg(ref_name), path_msg(ps),
                                  path_msg(dirslash)))
            reprogress()
    elif verbosity > 3:
        ps = b'/'.join(item.path)
        log('%s %s:%s%s\n' % (status, path_msg(ref_name), path_msg(ps), path_msg(dirslash)))


def find_live_objects(existing_count, cat_pipe, idx_list, refs=None,
                      verbosity=0, count_missing=False):
    pack_dir = git.repo(b'objects/pack')
    ffd, bloom_filename = tempfile.mkstemp(b'.bloom', b'tmp-gc-', pack_dir)
    os.close(ffd)
    # FIXME: allow selection of k?
    # FIXME: support ephemeral bloom filters (i.e. *never* written to disk)
    live_blobs = bloom.create(bloom_filename, expected=existing_count, k=None)
    with ExitStack() as maybe_close_bloom:
        maybe_close_bloom.enter_context(live_blobs)
        # live_blobs will hold on to the fd until close or exit
        os.unlink(bloom_filename)
        live_trees = set()
        stop_at = lambda x: unhexlify(x) in live_trees
        oid_exists = (lambda oid: idx_list.exists(oid)) if idx_list else None
        approx_live_count = 0
        missing = 0
        for ref_name, ref_id in refs if refs else git.list_refs():
            for item in walk_object(cat_pipe.get, hexlify(ref_id),
                                    stop_at=stop_at, include_data=None,
                                    oid_exists=oid_exists):
                if item.data is False:
                    if count_missing:
                        report_missing(ref_name, item, verbosity)
                        missing += 1
                    else:
                        raise MissingObject(item.oid)
                # FIXME: batch ids
                elif verbosity:
                    report_live_item(approx_live_count, existing_count,
                                     ref_name, ref_id, item, verbosity)
                if item.type != b'blob':
                    if verbosity and not item.oid in live_trees:
                        approx_live_count += 1
                    live_trees.add(item.oid)
                else:
                    if verbosity and not live_blobs.exists(item.oid):
                        approx_live_count += 1
                    live_blobs.add(item.oid)
        maybe_close_bloom.pop_all()
        if count_missing:
            return live_blobs, live_trees, missing
        else:
            return live_blobs, live_trees

_pack_stem_rx = re.compile(br'pack-[0-9a-fA-F]{40}')

def sweep(live_objects, live_trees, existing_count, cat_pipe, threshold,
          compression, verbosity):
    """Traverse all the packs, saving the (probably) live data."""

    stale_packs = [] # stems like /some/where/pack-OIDX (no suffix)

    def remove_stale_packs(new_pack_prefix):
        nonlocal stale_packs
        if new_pack_prefix:
            assert _pack_stem_rx.fullmatch(basename(new_pack_prefix))
            if verbosity:
                log('created ' + path_msg(basename(new_pack_prefix)) + '\n')
        for stem in stale_packs:
            assert _pack_stem_rx.fullmatch(basename(stem))
            if stem == new_pack_prefix:
                continue  # Don't remove the new pack file
            for p in glob.glob(stem + b'.*'):
                if verbosity:
                    log(f'removing {path_msg(basename(p))}\n')
                os.unlink(p)
        if verbosity: reprogress()
        if stale_packs:  # So git cat-pipe will close them
            cat_pipe.restart()
        stale_packs = []

    repo = LocalRepo(compression_level=compression,
                     objcache_maker=lambda _: None,
                     on_pack_finish=remove_stale_packs,
                     run_midx=False)
    try:
        # FIXME: sanity check .idx names vs .pack names?
        collect_count = 0
        for idx_name in glob.glob(os.path.join(git.repo(b'objects/pack'), b'*.idx')):
            if verbosity:
                qprogress('preserving live data (%d%% complete)\r'
                          % ((float(collect_count) / existing_count) * 100))
            with git.open_idx(idx_name) as idx:
                idx_live_count = 0
                must_rewrite = False
                live_in_this_pack = set()
                for sha in idx:
                    tmp_it = cat_pipe.get(hexlify(sha), include_data=False)
                    _, typ, _ = next(tmp_it)
                    if typ != b'blob':
                        is_live = sha in live_trees
                        if not is_live:
                            must_rewrite = True
                    else:
                        is_live = live_objects.exists(sha)
                    if is_live:
                        idx_live_count += 1
                        live_in_this_pack.add(sha)

                collect_count += idx_live_count
                if idx_live_count == 0:
                    if verbosity:
                        log('deleting %s\n'
                            % path_msg(git.repo_rel(basename(idx_name))))
                        reprogress()
                    assert idx_name.endswith(b'.idx')
                    stale_packs.append(idx_name[:-4])
                    continue

                live_frac = idx_live_count / float(len(idx))
                if not must_rewrite and live_frac > ((100 - threshold) / 100.0):
                    if verbosity:
                        keep_path = path_msg(git.repo_rel(basename(idx_name)))
                        log(f'keeping {keep_path} ({live_frac * 100}% live)\n')
                        reprogress()
                    continue

                if verbosity:
                    rw_path = path_msg(basename(idx_name))
                    log(f'rewriting {rw_path} ({live_frac * 100:.2f}% live)\n')
                    reprogress()
                for sha in idx:
                    if sha in live_in_this_pack:
                        item_it = cat_pipe.get(hexlify(sha))
                        _, typ, _ = next(item_it)
                        repo.just_write(sha, typ, b''.join(item_it))
                assert idx_name.endswith(b'.idx')
                stale_packs.append(idx_name[:-4])

        if verbosity:
            progress('preserving live data (%d%% complete)\n'
                     % ((float(collect_count) / existing_count) * 100))

        # Nothing should have recreated midx/bloom yet.
        pack_dir = git.repo(b'objects/pack')
        assert(not os.path.exists(os.path.join(pack_dir, b'bup.bloom')))
        assert(not glob.glob(os.path.join(pack_dir, b'*.midx')))

    except BaseException as ex:
        with pending_raise(ex):
            repo.abort_writing()
    finally:
        # This will finally run midx.
        repo.close()

    remove_stale_packs(None)  # In case we didn't write to the repo.

    if verbosity:
        log('discarded %d%% of objects\n'
            % ((existing_count - count_objects(pack_dir, verbosity))
               / float(existing_count) * 100))


def bup_gc(threshold=10, compression=1, verbosity=0, ignore_missing=False):
    cat_pipe = git.cp()
    existing_count = count_objects(git.repo(b'objects/pack'), verbosity)
    if verbosity:
        log('found %d objects\n' % existing_count)
        reprogress()
    if not existing_count:
        if verbosity:
            log('nothing to collect\n')
    else:
        try:
            with ExitStack() as maybe_close_idxl:
                idxl = None
                if ignore_missing:
                    idxl = git.PackIdxList(git.repo(b'objects/pack'))
                    maybe_close_idxl.enter_context(idxl)
                found = find_live_objects(existing_count, cat_pipe, idxl,
                                          verbosity=verbosity,
                                          count_missing=ignore_missing)
            live_objects, live_trees = found[:2]
            if verbosity:
                log('expecting to retain about %.2f%% unnecessary objects\n'
                    % live_objects.pfalse_positive())
                reprogress()
        except MissingObject as ex:
            log('bup: missing object %r \n' % hexstr(ex.oid))
            sys.exit(EXIT_FAILURE)
        with live_objects:
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
                sweep(live_objects, live_trees, existing_count, cat_pipe,
                      threshold, compression,
                      verbosity)
            except BaseException as ex:
                log('WARNING: Collection interrupted.  Run gc (again) to completion before\n'
                    'WARNING: adding any new data to the repository (e.g. via save or get).\n')
                raise ex
