
from io import BytesIO

from bup import hashsplit
from bup.hashsplit import \
    (BUP_TREE_BLOBBITS,
     GIT_MODE_TREE,
     GIT_MODE_FILE,
     split_to_blob_or_tree)
from bup.helpers import add_error
from bup.metadata import Metadata, MetadataRO
from bup.io import path_msg
from bup.git import shalist_item_sort_key, mangle_name
from bup._helpers import RecordHashSplitter


_empty_metadata = MetadataRO()

class TreeItem:
    __slots__ = 'name', 'mode', 'gitmode', 'oid', 'meta'
    def __init__(self, name, mode, gitmode, oid, meta):
        assert isinstance(name, bytes), name
        assert isinstance(mode, int), mode
        assert isinstance(gitmode, int), gitmode
        assert isinstance(oid, bytes), oid
        if meta is not None:
            assert isinstance(meta, Metadata), meta
        self.name = name
        self.mode = mode
        self.gitmode = gitmode
        self.oid = oid
        self.meta = meta or _empty_metadata
    def __repr__(self):
        return f'<bup.tree.TreeItem object at 0x{id(self):x} name={self.name!r}>'
    def mangled_name(self):
        return mangle_name(self.name, self.mode, self.gitmode)

class RawTreeItem(TreeItem):
    def mangled_name(self):
        return self.name

class SplitTreeItem(RawTreeItem):
    __slots__ = 'first_full_name', 'last_full_name'
    def __init__(self, name, treeid, first, last):
        super().__init__(name, GIT_MODE_TREE, GIT_MODE_TREE, treeid, None)
        self.first_full_name = first
        self.last_full_name = last

def _abbreviate_tree_names(names):
    """Return a list of unique abbreviations for the given names."""
    abbrev = {}
    # build a trie (using dicts) out of all the names
    for name in names:
        level = abbrev
        for c in name:
            if not c in level:
                # use None as the back-pointer, not a valid char
                # (fun for the GC to detect the cycles :-) )
                level[c] = {None: level}
            level = level[c]
    outnames = []
    # and abbreviate all the names
    for name in names:
        out = name
        level = abbrev
        for n in range(len(name)):
            level = level[name[n]]
        while True:
            # backtrack a level
            level = level[None]
            # if it has more than a single char & None,
            # we cannot abbreviate any further
            if len(level) > 2:
                break
            candidate = out[:-1]
            # of course we must not have an invalid name
            if candidate in (b'', b'.', b'..'):
                break;
            out = candidate
        outnames.append(out)
    return outnames

def _abbreviate_item_names(items):
    """Set each item's name to an abbreviation that's still unique
    with respect to the other items."""
    names = []
    for item in items:
        names.append(item.first_full_name)
    for item in items[:-1]:
        names.append(item.last_full_name)
    abbrevnames = _abbreviate_tree_names(names)
    for abbrev_name, item in zip(abbrevnames, items):
        item.name = abbrev_name


class StackDir:
    __slots__ = 'name', 'items', 'meta'

    def __init__(self, name, meta):
        self.name = name
        self.meta = meta
        self.items = []


class Stack:
    def __init__(self, repo, split_config):
        self._stack = []
        self._repo = repo
        self._split_config = split_config

    def __len__(self):
        return len(self._stack)

    def path(self):
        return [p.name for p in self._stack]

    def push(self, name, meta):
        assert isinstance(meta, (Metadata, type(None))), meta
        self._stack.append(StackDir(name, meta))

    def _clean(self, tree):
        names_seen = set()
        items = []
        for item in tree.items:
            if item.name in names_seen:
                parent_path = b'/'.join(n for n in self.path()) + b'/'
                add_error('error: ignoring duplicate path %s in %s'
                          % (path_msg(item.name), path_msg(parent_path)))
            else:
                names_seen.add(item.name)
                items.append(item)
        return items

    def _write_tree(self, dir_meta, items, add_meta=True):
        shalist = []
        # This might be False if doing a 'bup rewrite' where the original is
        # from an old repo without metadata, or created by 'bup split'.
        meta_ok = all(isinstance(entry.meta, Metadata)
                      for entry in items if entry.mode != GIT_MODE_TREE)
        if add_meta and meta_ok:
            metalist = [(b'', _empty_metadata if dir_meta is None else dir_meta)]
            metalist += [(shalist_item_sort_key((entry.mode, entry.name, None)),
                          entry.meta)
                         for entry in items if entry.mode != GIT_MODE_TREE]
            metalist.sort(key = lambda x: x[0])
            metadata = BytesIO(b''.join(m[1].encode() for m in metalist))
            splitter = hashsplit.from_config([metadata], self._split_config)
            mode, oid = split_to_blob_or_tree(self._repo.write_bupm,
                                              self._repo.write_tree,
                                              splitter)
            shalist.append((mode, b'.bupm', oid))
        shalist += [(entry.gitmode, entry.mangled_name(), entry.oid)
                    for entry in items]
        return self._repo.write_tree(shalist)

    def _write_split_tree(self, dir_meta, items, level=0):
        """Write a (possibly split) tree representing items.

        Write items as either a a single git tree object, or as a "split
        subtree"  See DESIGN for additional information.
        """
        assert level >= 0
        if not items:
            return self._write_tree(dir_meta, items)

        # We only feed the name into the hashsplitter because otherwise
        # minor changes (changing the content of the file, or changing a
        # dir to a file or vice versa) can have major ripple effects on
        # the layout of the split tree structure, which may then result in
        # a lot of extra objects being written.  Unfortunately this also
        # means that the trees will (on average) be larger (due to the 64
        # byte) window, but the expected chunk size is relatively small so
        # that shouldn't really be an issue.
        #
        # We also don't create subtrees with only a single entry (unless
        # they're the last entry), since that would not only be wasteful,
        # but also lead to recursion if some filename all by itself
        # contains a split point - since it's propagated to the next layer
        # up.  This leads to a worst-case depth of ceil(log2(# of names)),
        # which is somewhat wasteful, but not *that* bad. Other solutions
        # to this could be devised, e.g. applying some bit perturbation to
        # the names depending on the level.

        # As we recurse, we abbreviate all of the tree names except (of
        # course) those in the leaves, and we track the range of names in
        # a given subtree via the first_full_name and last_full_name
        # attributes, so we can use them to select the proper
        # abbreviations.  (See DESIGN for the constraints.)

        splits = []  # replacement trees for this level
        last_item = items[-1]
        pending_split = []
        h = RecordHashSplitter(bits=BUP_TREE_BLOBBITS)
        for item in items:
            pending_split.append(item)
            split, bits = h.feed(item.name)
            if (split and len(pending_split) > 1) or item is last_item:
                splits.append(pending_split)
                pending_split = []

        if len(splits) == 1:
            # If the level is 0, this is an unsplit tree, otherwise it's
            # the top of a split tree, so add the .bupd marker.
            if level > 0:
                assert len(items) == len(splits[0])
                assert all(lambda x, y: x is y for x, y in zip(items, splits[0]))
                _abbreviate_item_names(items)
                sentinel_sha = self._repo.write_data(b'')
                items.append(RawTreeItem(b'.bupd.%d.bupd' % level,
                                         GIT_MODE_FILE, GIT_MODE_FILE,
                                         sentinel_sha, None))
            return self._write_tree(dir_meta, items)

        # This tree level was split
        newtree = []
        if level == 0:  # Leaf nodes, just add them.
            for split_items in splits:
                newtree.append(SplitTreeItem(split_items[0].name,
                                             self._write_tree(None, split_items),
                                             split_items[0].name,
                                             split_items[-1].name))
        else:  # "inner" nodes (not top, not leaf), abbreviate names
            for split_items in splits:
                _abbreviate_item_names(split_items)
                # "internal" (not top, not leaf) trees don't have a .bupm
                newtree.append(SplitTreeItem(split_items[0].name,
                                             self._write_tree(None, split_items,
                                                              add_meta=False),
                                             split_items[0].first_full_name,
                                             split_items[-1].last_full_name))

        assert newtree
        return self._write_split_tree(dir_meta, newtree, level + 1)

    def _write(self, tree):
        items = self._clean(tree)
        if not self._split_config['trees']:
            return self._write_tree(tree.meta, items)
        items.sort(key=lambda x: x.name)
        return self._write_split_tree(tree.meta, items)

    def pop(self, override_tree=None, override_meta=None):
        tree = self._stack.pop()
        if override_meta is not None:
            tree.meta = override_meta
        if not override_tree: # caution - False happens, not just None
            tree_oid = self._write(tree)
        else:
            tree_oid = override_tree
        if len(self):
            self.append_to_current(tree.name, GIT_MODE_TREE, GIT_MODE_TREE,
                                   tree_oid, None)
        return tree_oid

    def append_to_current(self, name, mode, gitmode, oid, meta):
        self._stack[-1].items.append(TreeItem(name, mode, gitmode, oid, meta))
