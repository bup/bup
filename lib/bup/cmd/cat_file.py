

import re, stat, sys

from bup import options, git, vfs
from bup.compat import argv_bytes
from bup.helpers import EXIT_FAILURE, chunkyreader, log
from bup.io import byte_stream, path_msg as pm
from bup.repo import LocalRepo

optspec = """
bup cat-file [--meta|--bupm] /branch/revision/[path]
--
meta        print the target's metadata entry (decoded then reencoded) to stdout
bupm        print the target directory's .bupm file directly to stdout
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags_, extra = o.parse_bytes(argv[1:])

    git.check_repo_or_die()

    if not extra:
        o.fatal('must specify a target')
    if len(extra) > 1:
        o.fatal('only one target file allowed')
    if opt.bupm and opt.meta:
        o.fatal('--meta and --bupm are incompatible')

    target = argv_bytes(extra[0])

    if not re.match(br'/*[^/]+/[^/]+', target):
        o.fatal(f"path {pm(target)} doesn't include a branch and revision")

    with LocalRepo() as repo:
        resolved = vfs.resolve(repo, target, follow=False)
        leaf_item = resolved[-1][1]
        if not leaf_item:
            res_path = b'/'.join(name for name, item in resolved)
            log(f'error: cannot access {pm(res_path)} in {pm(target)}\n')
            sys.exit(EXIT_FAILURE)

        mode = vfs.item_mode(leaf_item)

        sys.stdout.flush()
        out = byte_stream(sys.stdout)

        if opt.bupm:
            if not stat.S_ISDIR(mode):
                o.fatal(f'{pm(target)} is not a directory')
            _, bupm_oid = vfs.tree_data_and_bupm(repo, leaf_item.oid)
            if bupm_oid:
                with vfs.tree_data_reader(repo, bupm_oid) as meta_stream:
                    out.write(meta_stream.read())
        elif opt.meta:
            augmented = vfs.augment_item_meta(repo, leaf_item, include_size=True)
            out.write(augmented.meta.encode())
        else:
            if stat.S_ISREG(mode):
                with vfs.fopen(repo, leaf_item) as f:
                    for b in chunkyreader(f):
                        out.write(b)
            else:
                o.fatal(f'{pm(target)} is not a plain file')
