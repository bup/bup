"""Common code for listing files from a bup repository."""

from __future__ import print_function
from itertools import chain
from stat import S_ISDIR, S_ISLNK
import copy, locale, os.path, stat, sys, xstat

from bup import metadata, options, vfs2 as vfs
from bup.repo import LocalRepo
from helpers import columnate, istty1, last, log

def item_hash(item, tree_for_commit):
    """If the item is a Commit, return its commit oid, otherwise return
    the item's oid, if it has one.

    """
    if tree_for_commit and isinstance(item, vfs.Commit):
        return item.coid
    return getattr(item, 'oid', None)

def item_info(item, name,
              show_hash = False,
              commit_hash=False,
              long_fmt = False,
              classification = None,
              numeric_ids = False,
              human_readable = False):
    """Return a string containing the information to display for the VFS
    item.  Classification may be "all", "type", or None.

    """
    result = ''
    if show_hash:
        oid = item_hash(item, commit_hash)
        result += '%s ' % (oid.encode('hex') if oid
                           else '0000000000000000000000000000000000000000')
    if long_fmt:
        meta = item.meta.copy()
        meta.path = name
        # FIXME: need some way to track fake vs real meta items?
        result += metadata.summary_str(meta,
                                       numeric_ids=numeric_ids,
                                       classification=classification,
                                       human_readable=human_readable)
    else:
        result += name
        if classification:
            result += xstat.classification_str(item.meta.mode,
                                               classification == 'all')
    return result


optspec = """
%sls [-a] [path...]
--
s,hash   show hash for each file
commit-hash show commit hash instead of tree for commits (implies -s)
a,all    show hidden files
A,almost-all    show hidden files except . and ..
l        use a detailed, long listing format
d,directory show directories, not contents; don't follow symlinks
F,classify append type indicator: dir/ sym@ fifo| sock= exec*
file-type append type indicator: dir/ sym@ fifo| sock=
human-readable    print human readable file sizes (i.e. 3.9K, 4.7M)
n,numeric-ids list numeric IDs (user, group, etc.) rather than names
"""

def do_ls(args, default='.', onabort=None, spec_prefix=''):
    """Output a listing of a file or directory in the bup repository.

    When a long listing is not requested and stdout is attached to a
    tty, the output is formatted in columns. When not attached to tty
    (for example when the output is piped to another command), one
    file is listed per line.

    """
    if onabort:
        o = options.Options(optspec % spec_prefix, onabort=onabort)
    else:
        o = options.Options(optspec % spec_prefix)
    (opt, flags, extra) = o.parse(args)

    # Handle order-sensitive options.
    classification = None
    show_hidden = None
    for flag in flags:
        (option, parameter) = flag
        if option in ('-F', '--classify'):
            classification = 'all'
        elif option == '--file-type':
            classification = 'type'
        elif option in ('-a', '--all'):
            show_hidden = 'all'
        elif option in ('-A', '--almost-all'):
            show_hidden = 'almost'

    if opt.commit_hash:
        opt.hash = True

    def item_line(item, name):
        return item_info(item, name,
                         show_hash = opt.hash,
                         commit_hash=opt.commit_hash,
                         long_fmt = opt.l,
                         classification = classification,
                         numeric_ids = opt.numeric_ids,
                         human_readable = opt.human_readable)

    repo = LocalRepo()
    ret = 0
    pending = []
    for path in (extra or [default]):
        try:
            if opt.directory:
                resolved = vfs.lresolve(repo, path)
            else:
                # FIXME: deal with invalid symlinks i.e. old vfs try_resolve
                resolved = vfs.resolve(repo, path)

            leaf_name, leaf_item = resolved[-1]
            if not leaf_item:
                log('error: cannot access %r in %r\n'
                    % ('/'.join(name for name, item in resolved),
                       path))
                ret = 1
                continue
            if not opt.directory and S_ISDIR(vfs.item_mode(leaf_item)):
                items = vfs.contents(repo, leaf_item)
                if show_hidden == 'all':
                    # Match non-bup "ls -a ... /".
                    parent = resolved[-2] if len(resolved) > 1 else resolved[0]
                    items = chain(items, (('..', parent[1]),))

                items = ((x[0], vfs.augment_item_meta(repo, x[1],
                                                      include_size=True))
                         for x in items)
                for sub_name, sub_item in sorted(items, key=lambda x: x[0]):
                    if show_hidden != 'all' and sub_name == '.':
                        continue
                    if sub_name.startswith('.') and \
                       show_hidden not in ('almost', 'all'):
                        continue
                    line = item_line(sub_item, sub_name)
                    pending.append(line) if not opt.l and istty1 else print(line)
            else:
                leaf_item = vfs.augment_item_meta(repo, leaf_item,
                                                  include_size=True)
                line = item_line(leaf_item, os.path.normpath(path))
                pending.append(line) if not opt.l and istty1 else print(line)
        except vfs.IOError as ex:
            log('bup: %s\n' % ex)
            ret = 1

    if pending:
        sys.stdout.write(columnate(pending, ''))

    return ret
