import os, errno, zlib, time, sha


def hash_raw(type, s):
    header = '%s %d\0' % (type, len(s))
    sum = sha.sha(header)
    sum.update(s)
    hex = sum.hexdigest()
    dir = '.git/objects/%s' % hex[0:2]
    fn = '%s/%s' % (dir, hex[2:])
    if not os.path.exists(fn):
        #log('creating %s' % fn)
        try:
            os.mkdir(dir)
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise
        tfn = '%s.%d' % (fn, os.getpid())
        f = open(tfn, 'w')
        z = zlib.compressobj(1)
        f.write(z.compress(header))
        f.write(z.compress(s))
        f.write(z.flush())
        f.close()
        os.rename(tfn, fn)
    else:
        #log('exists %s' % fn)
        pass
    return hex


def hash_blob(blob):
    return hash_raw('blob', blob)


def gen_tree(shalist):
    l = ['%s %s\0%s' % (mode,name,hex.decode('hex')) 
         for (mode,name,hex) in shalist]
    return hash_raw('tree', ''.join(l))


def _git_date(date):
    return time.strftime('%s %z', time.localtime(date))


def gen_commit(tree, parent, author, adate, committer, cdate, msg):
    l = []
    if tree: l.append('tree %s' % tree)
    if parent: l.append('parent %s' % parent)
    if author: l.append('author %s %s' % (author, _git_date(adate)))
    if committer: l.append('committer %s %s' % (committer, _git_date(cdate)))
    l.append('')
    l.append(msg)
    return hash_raw('commit', '\n'.join(l))
