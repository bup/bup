
from bup import git, options, vfs
from bup.compat import argv_bytes
from bup.gc import count_objects, find_live_objects
from bup.helpers import EXIT_FALSE, EXIT_SUCCESS, EXIT_TRUE, log, progress
from bup.io import path_msg
from bup.repo import LocalRepo


optspec = """
bup validate-refs [--links] [REF...]
--
links      report missing objects referred to by REFs
v,verbose  increase log output (can be used more than once)
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    verbosity = opt.verbose

    if opt.links is False:
        return EXIT_SUCCESS

    git.check_repo_or_die()
    cat_pipe = git.cp()

    ref_missing = 0
    ref_info = []
    with LocalRepo() as repo:
        for ref in [argv_bytes(x) for x in extra]:
            # FIXME: unify with other commands and git: vfs:, etc.
            res = vfs.try_resolve(repo, ref, want_meta=False)
            # FIXME: if symlink, error(dangling)
            # FIXME: IOError ENOTDIR ELOOP
            _, leaf = res[-1]
            if not leaf:
                log(f'missing {path_msg(ref)}')
                ref_missing += 1
                continue
            kind = type(leaf)
            # FIXME: Root Tags FakeLink
            if kind in (vfs.Item, vfs.Chunky, vfs.RevList):
                ref_info.append((ref, leaf.oid))
            elif kind == vfs.Commit:
                ref_info.append((ref, leaf.coid))
            else:
                o.fatal(f"can't currently handle VFS {kind} for {path_msg(ref)}")

    found_missing = 0
    # Wanted all refs, or at least some specified weren't missing
    if not extra or (extra and ref_info):
        existing_count = count_objects(git.repo(b'objects/pack'), verbosity)
        if verbosity:
            progress(f'found {existing_count} objects\r')

        if existing_count:
            with git.PackIdxList(git.repo(b'objects/pack')) as idxl:
                live_objects, live_trees, found_missing = \
                    find_live_objects(existing_count, cat_pipe, refs=ref_info,
                                      count_missing=True, idx_list=idxl,
                                      verbosity=verbosity)
                live_objects.close()

    return EXIT_FALSE if (ref_missing + found_missing) else EXIT_TRUE
