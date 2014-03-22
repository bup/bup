"""Common code for listing files from a bup repository."""
import copy, os.path, stat, xstat
from bup import metadata, options, vfs
from helpers import *


def node_info(n, name,
              show_hash = False,
              long_fmt = False,
              classification = None,
              numeric_ids = False,
              human_readable = False):
    """Return a string containing the information to display for the node
    n.  Classification may be "all", "type", or None."""
    result = ''
    if show_hash:
        result += "%s " % n.hash.encode('hex')
    if long_fmt:
        meta = copy.copy(n.metadata())
        if meta:
            meta.path = name
            meta.size = n.size()
        else:
            # Fake it -- summary_str() is designed to handle a fake.
            meta = metadata.Metadata()
            meta.size = n.size()
            meta.mode = n.mode
            meta.path = name
            meta.atime, meta.mtime, meta.ctime = n.atime, n.mtime, n.ctime
            if stat.S_ISLNK(meta.mode):
                meta.symlink_target = n.readlink()
        result += metadata.summary_str(meta,
                                       numeric_ids = numeric_ids,
                                       classification = classification,
                                       human_readable = human_readable)
    else:
        result += name
        if classification:
            mode = n.metadata() and n.metadata().mode or n.mode
            result += xstat.classification_str(mode, classification == 'all')
    return result


optspec = """
%sls [-a] [path...]
--
s,hash   show hash for each file
a,all    show hidden files
A,almost-all    show hidden files except . and ..
l        use a detailed, long listing format
d,directory show directories, not contents; don't follow symlinks
F,classify append type indicator: dir/ sym@ fifo| sock= exec*
file-type append type indicator: dir/ sym@ fifo| sock=
human-readable    print human readable file sizes (i.e. 3.9K, 4.7M)
n,numeric-ids list numeric IDs (user, group, etc.) rather than names
"""

def do_ls(args, pwd, default='.', onabort=None, spec_prefix=''):
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

    L = []
    def output_node_info(node, name):
        info = node_info(node, name,
                         show_hash = opt.hash,
                         long_fmt = opt.l,
                         classification = classification,
                         numeric_ids = opt.numeric_ids,
                         human_readable = opt.human_readable)
        if not opt.l and istty1:
            L.append(info)
        else:
            print info

    ret = 0
    for path in (extra or [default]):
        try:
            if opt.directory:
                n = pwd.lresolve(path)
            else:
                n = pwd.try_resolve(path)

            if not opt.directory and stat.S_ISDIR(n.mode):
                if show_hidden == 'all':
                    output_node_info(n, '.')
                    # Match non-bup "ls -a ... /".
                    if n.parent:
                        output_node_info(n.parent, '..')
                    else:
                        output_node_info(n, '..')
                for sub in n:
                    name = sub.name
                    if show_hidden in ('almost', 'all') \
                       or not len(name)>1 or not name.startswith('.'):
                        output_node_info(sub, name)
            else:
                output_node_info(n, os.path.normpath(path))
        except vfs.NodeError, e:
            log('error: %s\n' % e)
            ret = 1

    if L:
        sys.stdout.write(columnate(L, ''))

    return ret
