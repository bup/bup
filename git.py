import os, errno, zlib, time, sha, subprocess, struct, mmap
from helpers import *


class PackIndex:
    def __init__(self, filename):
        self.name = filename
        f = open(filename)
        self.map = mmap.mmap(f.fileno(), 0,
                             mmap.MAP_SHARED, mmap.PROT_READ)
        f.close()  # map will persist beyond file close
        assert(str(self.map[0:8]) == '\377tOc\0\0\0\2')
        self.fanout = list(struct.unpack('!256I', buffer(self.map, 8, 256*4)))
        self.fanout.append(0)  # entry "-1"
        nsha = self.fanout[255]
        self.ofstable = buffer(self.map,
                               8 + 256*4 + nsha*20 + nsha*4,
                               nsha*4)
        self.ofs64table = buffer(self.map,
                                 8 + 256*4 + nsha*20 + nsha*4 + nsha*4)

    def _ofs_from_idx(self, idx):
        ofs = struct.unpack('!I', buffer(self.ofstable, idx*4, 4))[0]
        if ofs & 0x80000000:
            idx64 = ofs & 0x7fffffff
            ofs = struct.unpack('!I', buffer(self.ofs64table, idx64*8, 8))[0]
        return ofs

    def _idx_from_hash(self, hash):
        assert(len(hash) == 20)
        b1 = ord(hash[0])
        start = self.fanout[b1-1] # range -1..254
        end = self.fanout[b1] # range 0..255
        buf = buffer(self.map, 8 + 256*4, end*20)
        want = buffer(hash)
        while start < end:
            mid = start + (end-start)/2
            v = buffer(buf, mid*20, 20)
            if v < want:
                start = mid+1
            elif v > want:
                end = mid
            else: # got it!
                return mid
        return None
    def find_offset(self, hash):
        idx = self._idx_from_hash(hash)
        if idx != None:
            return self._ofs_from_idx(idx)
        return None

    def exists(self, hash):
        return (self._idx_from_hash(hash) != None) and True or None


class MultiPackIndex:
    def __init__(self, dir):
        self.packs = []
        for f in os.listdir(dir):
            if f.endswith('.idx'):
                self.packs.append(PackIndex(os.path.join(dir, f)))

    def exists(self, hash):
        for i in range(len(self.packs)):
            p = self.packs[i]
            if p.exists(hash):
                # reorder so most recently used packs are searched first
                self.packs = [p] + self.packs[:i] + self.packs[i+1:]
                return True
        return None


def _old_write_object(bin, type, content):
    hex = bin.encode('hex')
    header = '%s %d\0' % (type, len(content))
    dir = '.git/objects/%s' % hex[0:2]
    fn = '%s/%s' % (dir, hex[2:])
    if not os.path.exists(fn):
        #log('creating %s' % fn)
        try:
            os.mkdir(dir)
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise
        tfn = '.git/objects/bup%d.tmp' % os.getpid()
        f = open(tfn, 'w')
        z = zlib.compressobj(1)
        f.write(z.compress(header))
        f.write(z.compress(content))
        f.write(z.flush())
        f.close()
        os.rename(tfn, fn)


def calc_hash(type, content):
    header = '%s %d\0' % (type, len(content))
    sum = sha.sha(header)
    sum.update(content)
    return sum.digest()


_typemap = dict(blob=3, tree=2, commit=1, tag=8)
class PackWriter:
    def __init__(self):
        self.count = 0
        self.binlist = []
        self.filename = '.git/objects/bup%d' % os.getpid()
        self.file = open(self.filename + '.pack', 'w+')
        self.file.write('PACK\0\0\0\2\0\0\0\0')

    def write(self, bin, type, content):
        global _typemap
        f = self.file

        sz = len(content)
        szbits = (sz & 0x0f) | (_typemap[type]<<4)
        sz >>= 4
        while 1:
            if sz: szbits |= 0x80
            f.write(chr(szbits))
            if not sz:
                break
            szbits = sz & 0x7f
            sz >>= 7
        
        z = zlib.compressobj(1)
        f.write(z.compress(content))
        f.write(z.flush())

        self.count += 1
        self.binlist.append(bin)
        return bin

    def easy_write(self, type, content):
        return self.write(calc_hash(type, content), type, content)

    def close(self):
        f = self.file

        # update object count
        f.seek(8)
        cp = struct.pack('!i', self.count)
        assert(len(cp) == 4)
        f.write(cp)

        # calculate the pack sha1sum
        f.seek(0)
        sum = sha.sha()
        while 1:
            b = f.read(65536)
            sum.update(b)
            if not b: break
        f.write(sum.digest())
        
        f.close()

        p = subprocess.Popen(['git', 'index-pack', '-v',
                              self.filename + '.pack'],
                             preexec_fn = lambda: _gitenv('.git'),
                             stdout = subprocess.PIPE)
        out = p.stdout.read().strip()
        if p.wait() or not out:
            raise Exception('git index-pack returned an error')
        nameprefix = '.git/objects/pack/%s' % out
        os.rename(self.filename + '.pack', nameprefix + '.pack')
        os.rename(self.filename + '.idx', nameprefix + '.idx')
        return nameprefix


_packout = None
def _write_object(bin, type, content):
    global _packout
    if not _packout:
        _packout = PackWriter()
    _packout.write(bin, type, content)


def flush_pack():
    global _packout
    if _packout:
        _packout.close()


_objcache = {}
def hash_raw(type, s):
    global _objcache
    bin = calc_hash(type, s)
    hex = bin.encode('hex')
    if bin in _objcache:
        return hex
    else:
        _write_object(bin, type, s)
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
