"""Common code for listing files from a bup repository."""
import stat
from bup import options, vfs
from helpers import *


def node_name(text, n, show_hash = False,
              show_filesize = False,
              filesize = None,
              human_readable = False):
    """Add symbols to a node's name to differentiate file types."""
    prefix = ''
    if show_hash:
        prefix += "%s " % n.hash.encode('hex')
    if show_filesize:
        if human_readable:
            prefix += "%10s " % format_filesize(filesize)
        else:
            prefix += "%14d " % filesize
    if stat.S_ISDIR(n.mode):
        return '%s%s/' % (prefix, text)
    elif stat.S_ISLNK(n.mode):
        return '%s%s@' % (prefix, text)
    else:
        return '%s%s' % (prefix, text)


optspec = """
%sls [-a] [path...]
--
s,hash   show hash for each file
a,all    show hidden files
l        show file sizes
human-readable    print human readable file sizes (i.e. 3.9K, 4.7M)
"""

def do_ls(args, pwd, default='.', onabort=None, spec_prefix=''):
    """Output a listing of a file or directory in the bup repository.

    When stdout is attached to a tty, the output is formatted in columns. When
    not attached to tty (for example when the output is piped to another
    command), one file is listed per line.
    """
    if onabort:
        o = options.Options(optspec % spec_prefix, onabort=onabort)
    else:
        o = options.Options(optspec % spec_prefix)
    (opt, flags, extra) = o.parse(args)

    L = []

    ret = 0
    for path in (extra or [default]):
        try:
            n = pwd.try_resolve(path)

            if stat.S_ISDIR(n.mode):
                for sub in n:
                    name = sub.name
                    fsize = sub.size() if opt.l else None
                    nname = node_name(name, sub, opt.hash, opt.l, fsize,
                                      opt.human_readable)
                    if opt.all or not len(name)>1 or not name.startswith('.'):
                        if istty1:
                            L.append(nname)
                        else:
                            print nname
            else:
                nname = node_name(path, n, opt.hash, opt.l, None,
                                  opt.human_readable)
                if istty1:
                    L.append(nname)
                else:
                    print nname
        except vfs.NodeError, e:
            log('error: %s\n' % e)
            ret = 1

    if istty1:
        sys.stdout.write(columnate(L, ''))

    return ret
