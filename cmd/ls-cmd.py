#!/usr/bin/env python
import sys, stat
from bup import options, git, vfs
from bup.helpers import *

def node_name(text, n):
    prefix = ''
    if opt.hash:
        prefix += "%s " % n.hash.encode('hex')
    if stat.S_ISDIR(n.mode):
        return '%s%s/' % (prefix, text)
    elif stat.S_ISLNK(n.mode):
        return '%s%s@' % (prefix, text)
    else:
        return '%s%s' % (prefix, text)


optspec = """
bup ls <dirs...>
--
s,hash   show hash for each file
a,all    show hidden files
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()
top = vfs.RefList(None)

if not extra:
    extra = ['/']

ret = 0
for d in extra:
    L = []
    try:
        n = top.lresolve(d)
        if stat.S_ISDIR(n.mode):
            for sub in n:
                if opt.all or not sub.name.startswith('.'):
                    if istty1:
                        L.append(node_name(sub.name, sub))
                    else:
                        print node_name(sub.name, sub)
        else:
            if opt.all or not n.name.startswith('.'):
                if istty1:
                    L.append(node_name(d, n))
                else:
                    print node_name(d, n)
    except vfs.NodeError, e:
        log('error: %s\n' % e)
        ret = 1

if istty1:
    sys.stdout.write(columnate(L, ''))

sys.exit(ret)
