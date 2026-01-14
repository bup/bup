"""Common code for listing files from a bup repository."""

from binascii import hexlify
from copy import deepcopy
from itertools import chain
from stat import S_ISDIR
import os.path
import posixpath

from bup import metadata, vfs, xstat
from bup.compat import argv_bytes
from bup.config import derive_repo_addr
from bup.io import path_msg
from bup.options import Options
from bup.repo import make_repo
from bup.helpers import columnate, istty1, log

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
    """Return bytes containing the information to display for the VFS
    item.  Classification may be "all", "type", or None.

    """
    result = []
    if show_hash:
        oid = item_hash(item, commit_hash)
        if oid:
            result.extend([hexlify(oid), b' '])
        else:
            result.append(b'0000000000000000000000000000000000000000 ')
    if long_fmt:
        meta = deepcopy(item.meta).thaw()
        meta.path = name
        # FIXME: need some way to track fake vs real meta items?
        result.append(metadata.summary_bytes(meta.freeze(),
                                             numeric_ids=numeric_ids,
                                             classification=classification,
                                             human_readable=human_readable))
    else:
        result.append(name)
        if classification:
            cls = xstat.classification_str(vfs.item_mode(item),
                                           classification == 'all')
            result.append(cls.encode('ascii'))
    return b''.join(result)


optspec = """
bup ls [-r host:path] [-l] [-d] [-F] [-a] [-A] [-s] [-n] [path...]
--
r,remote=   remote repository path
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

class LsOpts:
    __slots__ = ['paths', 'long_listing', 'classification', 'show_hidden',
                 'hash', 'commit_hash', 'numeric_ids', 'human_readable',
                 'directory', 'repo', 'l']

def opts_from_cmdline(args, onabort=None, pwd=b'/'):
    """Parse ls command line arguments and return a dictionary of ls
    options, agumented with "classification", "long_listing",
    "paths", and "show_hidden".

    """
    o = Options(optspec, onabort=onabort)
    opt, flags, extra = o.parse_bytes(args)
    opt.paths = [argv_bytes(x) for x in extra] or (pwd,)
    opt.long_listing = opt.l
    opt.classification = None
    opt.show_hidden = None
    for flag in flags:
        option, parameter = flag
        if option in ('-F', '--classify'):
            opt.classification = 'all'
        elif option == '--file-type':
            opt.classification = 'type'
        elif option in ('-a', '--all'):
            opt.show_hidden = 'all'
        elif option in ('-A', '--almost-all'):
            opt.show_hidden = 'almost'
    ret = LsOpts()
    ret.paths = opt.paths
    ret.l = ret.long_listing = opt.long_listing
    ret.classification = opt.classification
    ret.show_hidden = opt.show_hidden
    ret.hash = opt.hash
    ret.commit_hash = opt.commit_hash
    ret.numeric_ids = opt.numeric_ids
    ret.human_readable = opt.human_readable
    ret.directory = opt.directory
    remote = argv_bytes(opt.remote) if opt.remote else None
    ret.repo = derive_repo_addr(remote=remote, die=o.fatal)
    return ret

def within_repo(repo, opt, out, pwd=b''):

    if opt.commit_hash:
        opt.hash = True

    def item_line(item, name):
        return item_info(item, name,
                         show_hash=opt.hash,
                         commit_hash=opt.commit_hash,
                         long_fmt=opt.long_listing,
                         classification=opt.classification,
                         numeric_ids=opt.numeric_ids,
                         human_readable=opt.human_readable)

    ret = 0
    want_meta = bool(opt.long_listing or opt.classification)
    pending = []
    last_n = len(opt.paths) - 1
    for n, printpath in enumerate(opt.paths):
        path = posixpath.join(pwd, printpath)
        try:
            if last_n > 0:
                out.write(b'%s:\n' % printpath)

            if opt.directory:
                resolved = vfs.resolve(repo, path, follow=False)
            else:
                resolved = vfs.try_resolve(repo, path, want_meta=want_meta)

            leaf_name, leaf_item = resolved[-1]
            if not leaf_item:
                log('error: cannot access %r in %r\n'
                    % ('/'.join(path_msg(name) for name, item in resolved),
                       path_msg(path)))
                ret = 1
                continue
            if not opt.directory and S_ISDIR(vfs.item_mode(leaf_item)):
                items = vfs.contents(repo, leaf_item, want_meta=want_meta)
                if opt.show_hidden == 'all':
                    # Match non-bup "ls -a ... /".
                    parent = resolved[-2] if len(resolved) > 1 else resolved[0]
                    items = chain(items, ((b'..', parent[1]),))
                for sub_name, sub_item in sorted(items, key=lambda x: x[0]):
                    if opt.show_hidden != 'all' and sub_name == b'.':
                        continue
                    if sub_name.startswith(b'.') and \
                       opt.show_hidden not in ('almost', 'all'):
                        continue
                    if opt.l:
                        sub_item = vfs.ensure_item_has_metadata(repo, sub_item,
                                                                include_size=True,
                                                                public=True)
                    elif want_meta:
                        sub_item = vfs.augment_item_meta(repo, sub_item,
                                                         include_size=True,
                                                         public=True)
                    line = item_line(sub_item, sub_name)
                    if not opt.long_listing and istty1:
                        pending.append(line)
                    else:
                        out.write(line)
                        out.write(b'\n')
            else:
                if opt.long_listing:
                    leaf_item = vfs.augment_item_meta(repo, leaf_item,
                                                      include_size=True,
                                                      public=True)
                line = item_line(leaf_item, os.path.normpath(path))
                if not opt.long_listing and istty1:
                    pending.append(line)
                else:
                    out.write(line)
                    out.write(b'\n')
        except vfs.IOError as ex:
            log('bup: %s\n' % ex)
            ret = 1

        if pending:
            out.write(columnate(pending, b''))
            pending = []

        if n < last_n:
            out.write(b'\n')

    return ret

def via_cmdline(args, out=None, onabort=None):
    """Write a listing of a file or directory in the bup repository to out.

    When a long listing is not requested and stdout is attached to a
    tty, the output is formatted in columns. When not attached to tty
    (for example when the output is piped to another command), one
    file is listed per line.

    """
    assert out
    opt = opts_from_cmdline(args, onabort=onabort)
    with make_repo(opt.repo) as repo:
        return within_repo(repo, opt, out)
