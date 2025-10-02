
from binascii import hexlify
from contextlib import ExitStack
from stat import S_ISDIR

from bup import git, options, vfs
from bup.compat import argv_bytes
from bup.gc import count_objects, find_live_objects
from bup.git import BUP_CHUNKED, MissingObject, demangle_name, tree_iter
from bup.helpers import EXIT_FAILURE, EXIT_FALSE, EXIT_TRUE, log
from bup.metadata import Metadata
from bup.io import walk_path_msg, path_msg
from bup.repo import LocalRepo
from bup.vfs import tree_data_reader


optspec = """
bup validate-refs [--links] [--bupm] [REF...]
--
bupm       report broken bupm (path metadata) objects within REFs
links      report missing objects referred to by REFs
v,verbose  increase log output (can be used more than once)
"""

def expected_bup_entry_count_for_tree(tree_data):
    exp_n = 1 # for the parent dir
    for mode, mangled_name, oid in tree_iter(tree_data):
        if mangled_name.endswith(b'.bupd'):
            return 2
        if mangled_name == b'.bupm':
            continue
        name, kind = demangle_name(mangled_name, mode)
        if S_ISDIR(mode) and kind != BUP_CHUNKED:
            continue
        exp_n += 1
    return exp_n

def resolve_refs(repo, refs, fatal):
    ref_missing = 0
    ref_info = []
    for ref in refs:
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
            fatal(f"can't currently handle VFS {kind} for {path_msg(ref)}")
    return ref_missing, ref_info

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    verbosity = opt.verbose

    if (opt.links, opt.bupm) == (False, False):
        o.fatal('no validation requested')
    if (opt.links, opt.bupm) == (None, None):
        opt.links = opt.bupm = True

    git.check_repo_or_die()
    cat_pipe = git.cp()

    with LocalRepo() as repo:
        ref_missing, ref_info = \
            resolve_refs(repo, [argv_bytes(x) for x in extra], o.fatal)

        bad_bupm = 0
        abridged_bupm = 0
        found_missing = 0
        def notice_missing(ref_name, item_path):
            nonlocal found_missing
            found_missing += 1
            item = item_path[-1]
            imsg = walk_path_msg(ref_name, item_path)
            log(f'missing {item.oid.hex()} {imsg}\n')

        def for_item(ref_name, item_path):
             # Always notice missing objects; without --links won't be
             # comprehensive.
            item = item_path[-1]
            if item.data is False:
                notice_missing(ref_name, item_path)
                return True
            if not opt.bupm:
                return True

            nonlocal bad_bupm, abridged_bupm
            if item.name != b'.bupm':
                return True
            bupm_n = 0
            with tree_data_reader(repo, item.oid) as bupm:
                try:
                    while Metadata.read(bupm):
                        bupm_n += 1
                except MissingObject:
                    return True # bupm sub-item, will be handled by later for_item
                except Exception:
                    pm = walk_path_msg(ref_name, item_path)
                    raise Exception(f'Unable to parse .bupm at {pm}')
            parent = item_path[-2]
            info = vfs.get_ref(repo, hexlify(parent.oid))
            assert info[0], info
            exp_n = expected_bup_entry_count_for_tree(b''.join(info[3]))
            if bupm_n == exp_n:
                return True
            elif bupm_n > exp_n:
                bad_bupm += 1
                log(f'error: tree with extra bupm entries ({bupm_n} > {exp_n})'
                    f' (please report): {parent.oid.hex()}\n')
            else:
                abridged_bupm += 1
                imsg = walk_path_msg(ref_name, item_path)
                log(f'abridged-bupm {imsg}\n')
            return True

        # Wanted all refs, or at least some specified weren't missing
        if not extra or (extra and ref_info):
            existing_count = count_objects(git.repo(b'objects/pack'), verbosity)
            if verbosity:
                log(f'found {existing_count} objects\n')
            with ExitStack() as maybe_close_idxl:
                idxl = None
                if opt.links:
                    idxl = git.PackIdxList(git.repo(b'objects/pack'))
                    maybe_close_idxl.enter_context(idxl)
                live_objs, live_trees = \
                    find_live_objects(existing_count, cat_pipe,
                                      refs=ref_info,
                                      idx_list=idxl,
                                      for_item=for_item,
                                      verbosity=verbosity)
                live_objs.close()
        if bad_bupm:
            return EXIT_FAILURE
        elif (ref_missing + found_missing + abridged_bupm):
            if (ref_missing or found_missing) and not opt.links:
                log(f'note: missing object list may be incomplete without --links\n')
            return EXIT_FALSE
        else:
            return EXIT_TRUE
