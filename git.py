import os, errno, zlib, time, sha, subprocess
from helpers import *

_objcache = {}
def hash_raw(type, s):
    global _objcache
    header = '%s %d\0' % (type, len(s))
    sum = sha.sha(header)
    sum.update(s)
    bin = sum.digest()
    hex = sum.hexdigest()
    if bin in _objcache:
        return hex
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
    _objcache[bin] = 1
    return hex


def hash_blob(blob):
    return hash_raw('blob', blob)


def gen_tree(shalist):
    shalist = sorted(shalist, key = lambda x: x[1])
    l = ['%s %s\0%s' % (mode,name,hex.decode('hex')) 
         for (mode,name,hex) in shalist]
    return hash_raw('tree', ''.join(l))


def _git_date(date):
    return time.strftime('%s %z', time.localtime(date))


def _gitenv(repo):
    os.environ['GIT_DIR'] = os.path.abspath(repo)


def _read_ref(repo, refname):
    p = subprocess.Popen(['git', 'show-ref', '--', refname],
                         preexec_fn = lambda: _gitenv(repo),
                         stdout = subprocess.PIPE)
    out = p.stdout.read().strip()
    p.wait()
    if out:
        return out.split()[0]
    else:
        return None


def _update_ref(repo, refname, newval, oldval):
    if not oldval:
        oldval = ''
    p = subprocess.Popen(['git', 'update-ref', '--', refname, newval, oldval],
                         preexec_fn = lambda: _gitenv(repo))
    p.wait()
    return newval


def gen_commit(tree, parent, author, adate, committer, cdate, msg):
    l = []
    if tree: l.append('tree %s' % tree)
    if parent: l.append('parent %s' % parent)
    if author: l.append('author %s %s' % (author, _git_date(adate)))
    if committer: l.append('committer %s %s' % (committer, _git_date(cdate)))
    l.append('')
    l.append(msg)
    return hash_raw('commit', '\n'.join(l))


def gen_commit_easy(ref, tree, msg):
    now = time.time()
    userline = '%s <%s@%s>' % (userfullname(), username(), hostname())
    oldref = ref and _read_ref('.git', ref) or None
    commit = gen_commit(tree, oldref, userline, now, userline, now, msg)
    if ref:
        _update_ref('.git', ref, commit, oldref)
    return commit
