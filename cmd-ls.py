#!/usr/bin/env python
import sys, os, re, time
import options, git


def namesplit(path):
    path = re.sub(r'/+', '/', path)
    while 1:
        p2 = re.sub(r'/[^/]+/\.\.(/|$)', '/', path)  # handle ../ notation
        if p2 == path: break
        path = p2
    l = path.split('/', 3)
    ref = None
    date = None
    dir = None
    assert(l[0] == '')
    if len(l) > 1:
        ref = l[1] or None
    if len(l) > 2:
        date = l[2]
    if len(l) > 3:
        dir = l[3]
    return (ref, date, dir)


optspec = """
bup ls <dirs...>
--
s,hash   show hash for each file
"""
o = options.Options('bup ls', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()

if not extra:
    extra = ['/']

for d in extra:
    (ref, date, path) = namesplit(d)
    if not ref:
        for (name,sha) in git.list_refs():
            name = re.sub('^refs/heads/', '', name)
            if opt.hash:
                print '%s %s' % (sha.encode('hex'), name)
            else:
                print name
    elif not date:
        dates = list(git.rev_list(ref))
        dates.sort()
        for (date,commit) in dates:
            l = time.localtime(date)
            print repr((time.strftime('%Y-%m-%d-%H%M%S', l),commit))
    else:
        dates = list(git.rev_list(ref))
        dates.sort(reverse=True)
        try:
            dp = time.strptime(date, '%Y-%m-%d-%H%M%S')
        except ValueError:
            dp = time.strptime(date, '%Y-%m-%d')
        dt = time.mktime(dp)
        commit = None
        for (d,commit) in dates:
            if d <= dt: break
        assert(commit)
        it = cp.get('%s:%s' % (commit.encode('hex'), path or ''))
        type = it.next()
        if type == 'tree':
            for (mode,name,sha) in git._treeparse(''.join(it)):
                if opt.hash:
                    print '%s %s' % (sha.encode('hex'), name)
                else:
                    print name
        else:
            (dir,name) = os.path.split(path)
            if opt.hash:
                print '%s %s' % ('?', name)  # FIXME
            else:
                print name
