
from __future__ import absolute_import, print_function
from collections import namedtuple
from stat import S_ISDIR

from bup import vfs
from bup.metadata import Metadata
from bup.git import BUP_CHUNKED

TreeDictValue = namedtuple('TreeDictValue', ('name', 'oid', 'meta'))

def tree_items(repo, oid):
    """Yield (name, entry_oid, meta) for each entry in oid.  meta will be
    a Metadata object for any non-directories and for '.', otherwise
    None.

    """
    # This is a simpler approach than the one in the vfs, used to
    # cross-check its behavior.
    tree_data, bupm_oid = vfs.tree_data_and_bupm(repo, oid)
    bupm = vfs._FileReader(repo, bupm_oid) if bupm_oid else None
    try:
        maybe_meta = lambda : Metadata.read(bupm) if bupm else None
        m = maybe_meta()
        if m and m.size is None:
            m.size = 0
        yield TreeDictValue(name=b'.', oid=oid, meta=m)
        tree_ents = vfs.ordered_tree_entries(tree_data, bupm=True)
        for name, mangled_name, kind, gitmode, sub_oid in tree_ents:
            if mangled_name == b'.bupm':
                continue
            assert name != b'.'
            if S_ISDIR(gitmode):
                if kind == BUP_CHUNKED:
                    yield TreeDictValue(name=name, oid=sub_oid,
                                        meta=maybe_meta())
                else:
                    yield TreeDictValue(name=name, oid=sub_oid,
                                        meta=vfs.default_dir_mode)
            else:
                yield TreeDictValue(name=name, oid=sub_oid, meta=maybe_meta())
    finally:
        if bupm:
            bupm.close()

def tree_dict(repo, oid):
    return dict((x.name, x) for x in tree_items(repo, oid))
