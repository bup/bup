"""Common code for listing files from a bup repository."""
import stat
from bup import options, vfs
from helpers import *


def node_name(text, n, show_hash):
    """Add symbols to a node's name to differentiate file types."""
    prefix = ''
    if show_hash:
        prefix += "%s " % n.hash.encode('hex')
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
                    if opt.all or not len(name)>1 or not name.startswith('.'):
                        if istty1:
                            L.append(node_name(name, sub, opt.hash))
                        else:
                            print node_name(name, sub, opt.hash)
            else:
                if istty1:
                    L.append(node_name(path, n, opt.hash))
                else:
                    print node_name(path, n, opt.hash)
        except vfs.NodeError, e:
            log('error: %s\n' % e)
            ret = 1

    if istty1:
        sys.stdout.write(columnate(L, ''))

    return ret
