import os, errno, zlib, time, sha, subprocess, struct, mmap, stat, re
from helpers import *

verbose = 0
home_repodir = os.path.expanduser('~/.bup')
repodir = None


class GitError(Exception):
    pass


def repo(sub = ''):
    global repodir
    if not repodir:
        raise GitError('You should call check_repo_or_die()')
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
        self.dir = dir
        self.also = {}
        self.packs = []
        for f in os.listdir(self.dir):
            if f.endswith('.idx'):
                self.packs.append(PackIndex(os.path.join(self.dir, f)))

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
    def __init__(self, objcache_maker=None):
        self.count = 0
        self.outbytes = 0
        self.filename = None
        self.file = None
        self.objcache_maker = objcache_maker
        self.objcache = None

    def __del__(self):
        self.close()

    def _make_objcache(self):
        if not self.objcache:
            if self.objcache_maker:
                self.objcache = self.objcache_maker()
            else:
                self.objcache = MultiPackIndex(repo('objects/pack'))

    def _open(self):
        if not self.file:
            self._make_objcache()
            self.filename = repo('objects/bup%d' % os.getpid())
            self.file = open(self.filename + '.pack', 'w+')
            self.file.write('PACK\0\0\0\2\0\0\0\0')

    def _raw_write(self, datalist):
        self._open()
        f = self.file
        for d in datalist:
            f.write(d)
            self.outbytes += len(d)
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

    def breakpoint(self):
        id = self._end()
        self.outbytes = self.count = 0
        return id

    def write(self, type, content):
        return self._write(calc_hash(type, content), type, content)

    def maybe_write(self, type, content):
        bin = calc_hash(type, content)
        if not self.objcache:
            self._make_objcache()
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
        if parent: l.append('parent %s' % parent.encode('hex'))
        if author: l.append('author %s %s' % (author, _git_date(adate)))
        if committer: l.append('committer %s %s' % (committer, _git_date(cdate)))
        l.append('')
        l.append(msg)
        return self.maybe_write('commit', '\n'.join(l))

    def new_commit(self, parent, tree, msg):
        now = time.time()
        userline = '%s <%s@%s>' % (userfullname(), username(), hostname())
        commit = self._new_commit(tree, parent,
                                  userline, now, userline, now,
                                  msg)
        return commit

    def abort(self):
        f = self.file
        if f:
            self.file = None
            f.close()
            os.unlink(self.filename + '.pack')

    def _end(self):
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
        self.objcache = None

        p = subprocess.Popen(['git', 'index-pack', '-v',
                              '--index-version=2',
                              self.filename + '.pack'],
                             preexec_fn = _gitenv,
                             stdout = subprocess.PIPE)
        out = p.stdout.read().strip()
        _git_wait('git index-pack', p)
        if not out:
            raise GitError('git index-pack produced no output')
        nameprefix = repo('objects/pack/%s' % out)
        os.rename(self.filename + '.pack', nameprefix + '.pack')
        os.rename(self.filename + '.idx', nameprefix + '.idx')
        return nameprefix

    def close(self):
        return self._end()


def _git_date(date):
    return time.strftime('%s %z', time.localtime(date))


def _gitenv():
    os.environ['GIT_DIR'] = os.path.abspath(repo())


def read_ref(refname):
    p = subprocess.Popen(['git', 'show-ref', '--', refname],
                         preexec_fn = _gitenv,
                         stdout = subprocess.PIPE)
    out = p.stdout.read().strip()
    rv = p.wait()  # not fatal
    if rv:
        assert(not out)
    if out:
        return out.split()[0].decode('hex')
    else:
        return None


def update_ref(refname, newval, oldval):
    if not oldval:
        oldval = ''
    p = subprocess.Popen(['git', 'update-ref', '--', refname,
                          newval.encode('hex'), oldval.encode('hex')],
                         preexec_fn = _gitenv)
    _git_wait('git update-ref', p)


def guess_repo(path=None):
    global repodir
    if path:
        repodir = path
    if not repodir:
        repodir = os.environ.get('BUP_DIR')
        if not repodir:
            repodir = os.path.expanduser('~/.bup')


def init_repo(path=None):
    guess_repo(path)
    d = repo()
    if os.path.exists(d) and not os.path.isdir(os.path.join(d, '.')):
        raise GitError('"%d" exists but is not a directory\n' % d)
    p = subprocess.Popen(['git', '--bare', 'init'], stdout=sys.stderr,
                         preexec_fn = _gitenv)
    _git_wait('git init', p)
    p = subprocess.Popen(['git', 'config', 'pack.indexVersion', '2'],
                         stdout=sys.stderr, preexec_fn = _gitenv)
    _git_wait('git config', p)


def check_repo_or_die(path=None):
    guess_repo(path)
    if not os.path.isdir(repo('objects/pack/.')):
        if repodir == home_repodir:
            init_repo()
        else:
            log('error: %r is not a bup/git repository\n' % repo())
            exit(15)


def _treeparse(buf):
    ofs = 0
    while ofs < len(buf):
        z = buf[ofs:].find('\0')
        assert(z > 0)
        spl = buf[ofs:ofs+z].split(' ', 1)
        assert(len(spl) == 2)
        sha = buf[ofs+z+1:ofs+z+1+20]
        ofs += z+1+20
        yield (spl[0], spl[1], sha)

_ver = None
def ver():
    global _ver
    if not _ver:
        p = subprocess.Popen(['git', '--version'],
                             stdout=subprocess.PIPE)
        gvs = p.stdout.read()
        _git_wait('git --version', p)
        m = re.match(r'git version (\S+.\S+)', gvs)
        if not m:
            raise GitError('git --version weird output: %r' % gvs)
        _ver = tuple(m.group(1).split('.'))
    needed = ('1','5','4')
    if _ver < needed:
        raise GitError('git version %s or higher is required; you have %s'
                       % ('.'.join(needed), '.'.join(_ver)))
    return _ver


def _git_wait(cmd, p):
    rv = p.wait()
    if rv != 0:
        raise GitError('%s returned %d' % (cmd, rv))


def _git_capture(argv):
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, preexec_fn = _gitenv)
    r = p.stdout.read()
    _git_wait(repr(argv), p)
    return r


_ver_warned = 0
class CatPipe:
    def __init__(self):
        global _ver_warned
        wanted = ('1','5','6')
        if ver() < wanted:
            if not _ver_warned:
                log('warning: git version < %s; bup will be slow.\n'
                    % '.'.join(wanted))
                _ver_warned = 1
            self.get = self._slow_get
        else:
            self.p = subprocess.Popen(['git', 'cat-file', '--batch'],
                                      stdin=subprocess.PIPE, 
                                      stdout=subprocess.PIPE,
                                      preexec_fn = _gitenv)
            self.get = self._fast_get

    def _fast_get(self, id):
        assert(id.find('\n') < 0)
        assert(id.find('\r') < 0)
        assert(id[0] != '-')
        self.p.stdin.write('%s\n' % id)
        hdr = self.p.stdout.readline()
        if hdr.endswith(' missing\n'):
            raise GitError('blob %r is missing' % id)
        spl = hdr.split(' ')
        if len(spl) != 3 or len(spl[0]) != 40:
            raise GitError('expected blob, got %r' % spl)
        (hex, type, size) = spl
        yield type
        for blob in chunkyreader(self.p.stdout, int(spl[2])):
            yield blob
        assert(self.p.stdout.readline() == '\n')

    def _slow_get(self, id):
        assert(id.find('\n') < 0)
        assert(id.find('\r') < 0)
        assert(id[0] != '-')
        type = _git_capture(['git', 'cat-file', '-t', id]).strip()
        yield type

        p = subprocess.Popen(['git', 'cat-file', type, id],
                             stdout=subprocess.PIPE,
                             preexec_fn = _gitenv)
        for blob in chunkyreader(p.stdout):
            yield blob
        _git_wait('git cat-file', p)

    def _join(self, it):
        type = it.next()
        if type == 'blob':
            for blob in it:
                yield blob
        elif type == 'tree':
            treefile = ''.join(it)
            for (mode, name, sha) in _treeparse(treefile):
                for blob in self.join(sha.encode('hex')):
                    yield blob
        elif type == 'commit':
            treeline = ''.join(it).split('\n')[0]
            assert(treeline.startswith('tree '))
            for blob in self.join(treeline[5:]):
                yield blob
        else:
            raise GitError('invalid object type %r: expected blob/tree/commit'
                           % type)

    def join(self, id):
        for d in self._join(self.get(id)):
            yield d
        

def cat(id):
    c = CatPipe()
    for d in c.join(id):
        yield d
