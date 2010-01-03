import os, errno, zlib, time, sha, subprocess, struct, mmap, stat
from helpers import *

verbose = 0
repodir = os.environ.get('BUP_DIR', '.git')

def repo(sub = ''):
    global repodir
    gd = os.path.join(repodir, '.git')
    if os.path.exists(gd):
        repodir = gd
    return os.path.join(repodir, sub)


class PackIndex:
    def __init__(self, filename):
        self.name = filename
        f = open(filename)
        self.map = mmap.mmap(f.fileno(), 0,
                             mmap.MAP_SHARED, mmap.PROT_READ)
        f.close()  # map will persist beyond file close
        assert(str(self.map[0:8]) == '\377tOc\0\0\0\2')
        self.fanout = list(struct.unpack('!256I',
                                         str(buffer(self.map, 8, 256*4))))
        self.fanout.append(0)  # entry "-1"
        nsha = self.fanout[255]
        self.ofstable = buffer(self.map,
                               8 + 256*4 + nsha*20 + nsha*4,
                               nsha*4)
        self.ofs64table = buffer(self.map,
                                 8 + 256*4 + nsha*20 + nsha*4 + nsha*4)

    def _ofs_from_idx(self, idx):
        ofs = struct.unpack('!I', str(buffer(self.ofstable, idx*4, 4)))[0]
        if ofs & 0x80000000:
            idx64 = ofs & 0x7fffffff
            ofs = struct.unpack('!I',
                                str(buffer(self.ofs64table, idx64*8, 8)))[0]
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
        self.also = {}
        for f in os.listdir(dir):
            if f.endswith('.idx'):
                self.packs.append(PackIndex(os.path.join(dir, f)))

    def exists(self, hash):
        if hash in self.also:
            return True
        for i in range(len(self.packs)):
            p = self.packs[i]
            if p.exists(hash):
                # reorder so most recently used packs are searched first
                self.packs = [p] + self.packs[:i] + self.packs[i+1:]
                return True
        return None

    def add(self, hash):
        self.also[hash] = 1

    def zap_also(self):
        self.also = {}


def calc_hash(type, content):
    header = '%s %d\0' % (type, len(content))
    sum = sha.sha(header)
    sum.update(content)
    return sum.digest()


def _shalist_sort_key(ent):
    (mode, name, id) = ent
    if stat.S_ISDIR(int(mode, 8)):
        return name + '/'
    else:
        return name


_typemap = dict(blob=3, tree=2, commit=1, tag=8)
class PackWriter:
    def __init__(self, objcache=None):
        self.count = 0
        self.filename = None
        self.file = None
        self.objcache = objcache or MultiPackIndex(repo('objects/pack'))

    def __del__(self):
        self.close()

    def _open(self):
        assert(not self.file)
        self.objcache.zap_also()
        self.filename = repo('objects/bup%d' % os.getpid())
        self.file = open(self.filename + '.pack', 'w+')
        self.file.write('PACK\0\0\0\2\0\0\0\0')

    def _raw_write(self, datalist):
        if not self.file:
            self._open()
        f = self.file
        for d in datalist:
            f.write(d)
        self.count += 1

    def _write(self, bin, type, content):
        if verbose:
            log('>')

        out = []

        sz = len(content)
        szbits = (sz & 0x0f) | (_typemap[type]<<4)
        sz >>= 4
        while 1:
            if sz: szbits |= 0x80
            out.append(chr(szbits))
            if not sz:
                break
            szbits = sz & 0x7f
            sz >>= 7

        z = zlib.compressobj(1)
        out.append(z.compress(content))
        out.append(z.flush())

        self._raw_write(out)
        return bin

    def write(self, type, content):
        return self._write(calc_hash(type, content), type, content)

    def maybe_write(self, type, content):
        bin = calc_hash(type, content)
        if not self.objcache.exists(bin):
            self._write(bin, type, content)
            self.objcache.add(bin)
        return bin

    def new_blob(self, blob):
        return self.maybe_write('blob', blob)

    def new_tree(self, shalist):
        shalist = sorted(shalist, key = _shalist_sort_key)
        l = ['%s %s\0%s' % (mode,name,bin) 
             for (mode,name,bin) in shalist]
        return self.maybe_write('tree', ''.join(l))

    def _new_commit(self, tree, parent, author, adate, committer, cdate, msg):
        l = []
        if tree: l.append('tree %s' % tree.encode('hex'))
        if parent: l.append('parent %s' % parent)
        if author: l.append('author %s %s' % (author, _git_date(adate)))
        if committer: l.append('committer %s %s' % (committer, _git_date(cdate)))
        l.append('')
        l.append(msg)
        return self.maybe_write('commit', '\n'.join(l))

    def new_commit(self, ref, tree, msg):
        now = time.time()
        userline = '%s <%s@%s>' % (userfullname(), username(), hostname())
        oldref = ref and _read_ref(ref) or None
        commit = self._new_commit(tree, oldref,
                                  userline, now, userline, now,
                                  msg)
        if ref:
            self.close()  # UGLY: needed so _update_ref can see the new objects
            _update_ref(ref, commit.encode('hex'), oldref)
        return commit

    def abort(self):
        f = self.file
        if f:
            self.file = None
            f.close()
            os.unlink(self.filename + '.pack')

    def close(self):
        f = self.file
        if not f: return None
        self.file = None

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
                             preexec_fn = _gitenv,
                             stdout = subprocess.PIPE)
        out = p.stdout.read().strip()
        if p.wait() or not out:
            raise Exception('git index-pack returned an error')
        nameprefix = repo('objects/pack/%s' % out)
        os.rename(self.filename + '.pack', nameprefix + '.pack')
        os.rename(self.filename + '.idx', nameprefix + '.idx')
        return nameprefix


class PackWriter_Remote(PackWriter):
    def __init__(self, conn, objcache=None):
        PackWriter.__init__(self, objcache)
        self.file = conn
        self.filename = 'remote socket'

    def _open(self):
        assert(not "can't reopen a PackWriter_Remote")

    def close(self):
        if self.file:
            self.file.write('\0\0\0\0')
        self.file = None

    def _raw_write(self, datalist):
        assert(self.file)
        data = ''.join(datalist)
        assert(len(data))
        self.file.write(struct.pack('!I', len(data)) + data)


def _git_date(date):
    return time.strftime('%s %z', time.localtime(date))


def _gitenv():
    os.environ['GIT_DIR'] = os.path.abspath(repo())


def _read_ref(refname):
    p = subprocess.Popen(['git', 'show-ref', '--', refname],
                         preexec_fn = _gitenv,
                         stdout = subprocess.PIPE)
    out = p.stdout.read().strip()
    p.wait()
    if out:
        return out.split()[0]
    else:
        return None


def _update_ref(refname, newval, oldval):
    if not oldval:
        oldval = ''
    p = subprocess.Popen(['git', 'update-ref', '--', refname, newval, oldval],
                         preexec_fn = _gitenv)
    p.wait()
    return newval


def init_repo():
    d = repo()
    if os.path.exists(d) and not os.path.isdir(os.path.join(d, '.')):
        raise Exception('"%d" exists but is not a directory\n' % d)
    p = subprocess.Popen(['git', 'init', '--bare'],
                         preexec_fn = _gitenv)
    return p.wait()


def check_repo_or_die():
    if not os.path.isdir(repo('objects/pack/.')):
        log('error: %r is not a bup/git repository\n' % repo())
        exit(15)
