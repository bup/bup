"""Git interaction library.
bup repositories are in Git format. This library allows us to
interact with the Git data structures.
"""
import os, zlib, time, subprocess, struct, stat, re, tempfile
import heapq
from bup.helpers import *
from bup import _helpers

MIDX_VERSION = 2

verbose = 0
ignore_midx = 0
home_repodir = os.path.expanduser('~/.bup')
repodir = None

_typemap =  { 'blob':3, 'tree':2, 'commit':1, 'tag':4 }
_typermap = { 3:'blob', 2:'tree', 1:'commit', 4:'tag' }

_total_searches = 0
_total_steps = 0


class GitError(Exception):
    pass


def repo(sub = ''):
    """Get the path to the git repository or one of its subdirectories."""
    global repodir
    if not repodir:
        raise GitError('You should call check_repo_or_die()')

    # If there's a .git subdirectory, then the actual repo is in there.
    gd = os.path.join(repodir, '.git')
    if os.path.exists(gd):
        repodir = gd

    return os.path.join(repodir, sub)


def auto_midx(objdir):
    main_exe = os.environ.get('BUP_MAIN_EXE') or sys.argv[0]
    args = [main_exe, 'midx', '--auto', '--dir', objdir]
    rv = subprocess.call(args, stdout=open('/dev/null', 'w'))
    if rv:
        add_error('%r: returned %d' % (args, rv))


def mangle_name(name, mode, gitmode):
    """Mangle a file name to present an abstract name for segmented files.
    Mangled file names will have the ".bup" extension added to them. If a
    file's name already ends with ".bup", a ".bupl" extension is added to
    disambiguate normal files from semgmented ones.
    """
    if stat.S_ISREG(mode) and not stat.S_ISREG(gitmode):
        return name + '.bup'
    elif name.endswith('.bup') or name[:-1].endswith('.bup'):
        return name + '.bupl'
    else:
        return name


(BUP_NORMAL, BUP_CHUNKED) = (0,1)
def demangle_name(name):
    """Remove name mangling from a file name, if necessary.

    The return value is a tuple (demangled_filename,mode), where mode is one of
    the following:

    * BUP_NORMAL  : files that should be read as-is from the repository
    * BUP_CHUNKED : files that were chunked and need to be assembled

    For more information on the name mangling algorythm, see mangle_name()
    """
    if name.endswith('.bupl'):
        return (name[:-5], BUP_NORMAL)
    elif name.endswith('.bup'):
        return (name[:-4], BUP_CHUNKED)
    else:
        return (name, BUP_NORMAL)


def _encode_packobj(type, content):
    szout = ''
    sz = len(content)
    szbits = (sz & 0x0f) | (_typemap[type]<<4)
    sz >>= 4
    while 1:
        if sz: szbits |= 0x80
        szout += chr(szbits)
        if not sz:
            break
        szbits = sz & 0x7f
        sz >>= 7
    z = zlib.compressobj(1)
    yield szout
    yield z.compress(content)
    yield z.flush()


def _encode_looseobj(type, content):
    z = zlib.compressobj(1)
    yield z.compress('%s %d\0' % (type, len(content)))
    yield z.compress(content)
    yield z.flush()


def _decode_looseobj(buf):
    assert(buf);
    s = zlib.decompress(buf)
    i = s.find('\0')
    assert(i > 0)
    l = s[:i].split(' ')
    type = l[0]
    sz = int(l[1])
    content = s[i+1:]
    assert(type in _typemap)
    assert(sz == len(content))
    return (type, content)


def _decode_packobj(buf):
    assert(buf)
    c = ord(buf[0])
    type = _typermap[(c & 0x70) >> 4]
    sz = c & 0x0f
    shift = 4
    i = 0
    while c & 0x80:
        i += 1
        c = ord(buf[i])
        sz |= (c & 0x7f) << shift
        shift += 7
        if not (c & 0x80):
            break
    return (type, zlib.decompress(buf[i+1:]))


class PackIdx:
    """Object representation of a Git pack index file."""
    def __init__(self, filename):
        self.name = filename
        self.idxnames = [self.name]
        self.map = mmap_read(open(filename))
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
        global _total_searches, _total_steps
        _total_searches += 1
        assert(len(hash) == 20)
        b1 = ord(hash[0])
        start = self.fanout[b1-1] # range -1..254
        end = self.fanout[b1] # range 0..255
        buf = buffer(self.map, 8 + 256*4, end*20)
        want = str(hash)
        _total_steps += 1  # lookup table is a step
        while start < end:
            _total_steps += 1
            mid = start + (end-start)/2
            v = str(buf[mid*20:(mid+1)*20])
            if v < want:
                start = mid+1
            elif v > want:
                end = mid
            else: # got it!
                return mid
        return None

    def find_offset(self, hash):
        """Get the offset of an object inside the index file."""
        idx = self._idx_from_hash(hash)
        if idx != None:
            return self._ofs_from_idx(idx)
        return None

    def exists(self, hash):
        """Return nonempty if the object exists in this index."""
        return hash and (self._idx_from_hash(hash) != None) and True or None

    def __iter__(self):
        for i in xrange(self.fanout[255]):
            yield buffer(self.map, 8 + 256*4 + 20*i, 20)

    def __len__(self):
        return int(self.fanout[255])


extract_bits = _helpers.extract_bits


class PackMidx:
    """Wrapper which contains data from multiple index files.
    Multiple index (.midx) files constitute a wrapper around index (.idx) files
    and make it possible for bup to expand Git's indexing capabilities to vast
    amounts of files.
    """
    def __init__(self, filename):
        self.name = filename
        self.force_keep = False
        assert(filename.endswith('.midx'))
        self.map = mmap_read(open(filename))
        if str(self.map[0:4]) != 'MIDX':
            log('Warning: skipping: invalid MIDX header in %r\n' % filename)
            self.force_keep = True
            return self._init_failed()
        ver = struct.unpack('!I', self.map[4:8])[0]
        if ver < MIDX_VERSION:
            log('Warning: ignoring old-style (v%d) midx %r\n' 
                % (ver, filename))
            self.force_keep = False  # old stuff is boring  
            return self._init_failed()
        if ver > MIDX_VERSION:
            log('Warning: ignoring too-new (v%d) midx %r\n'
                % (ver, filename))
            self.force_keep = True  # new stuff is exciting
            return self._init_failed()

        self.bits = _helpers.firstword(self.map[8:12])
        self.entries = 2**self.bits
        self.fanout = buffer(self.map, 12, self.entries*4)
        shaofs = 12 + self.entries*4
        nsha = self._fanget(self.entries-1)
        self.shalist = buffer(self.map, shaofs, nsha*20)
        self.idxnames = str(self.map[shaofs + 20*nsha:]).split('\0')

    def _init_failed(self):
        self.bits = 0
        self.entries = 1
        self.fanout = buffer('\0\0\0\0')
        self.shalist = buffer('\0'*20)
        self.idxnames = []

    def _fanget(self, i):
        start = i*4
        s = self.fanout[start:start+4]
        return _helpers.firstword(s)

    def _get(self, i):
        return str(self.shalist[i*20:(i+1)*20])

    def exists(self, hash):
        """Return nonempty if the object exists in the index files."""
        global _total_searches, _total_steps
        _total_searches += 1
        want = str(hash)
        el = extract_bits(want, self.bits)
        if el:
            start = self._fanget(el-1)
            startv = el << (32-self.bits)
        else:
            start = 0
            startv = 0
        end = self._fanget(el)
        endv = (el+1) << (32-self.bits)
        _total_steps += 1   # lookup table is a step
        hashv = _helpers.firstword(hash)
        #print '(%08x) %08x %08x %08x' % (extract_bits(want, 32), startv, hashv, endv)
        while start < end:
            _total_steps += 1
            #print '! %08x %08x %08x   %d - %d' % (startv, hashv, endv, start, end)
            mid = start + (hashv-startv)*(end-start-1)/(endv-startv)
            #print '  %08x %08x %08x   %d %d %d' % (startv, hashv, endv, start, mid, end)
            v = self._get(mid)
            #print '    %08x' % self._num(v)
            if v < want:
                start = mid+1
                startv = _helpers.firstword(v)
            elif v > want:
                end = mid
                endv = _helpers.firstword(v)
            else: # got it!
                return True
        return None

    def __iter__(self):
        for i in xrange(self._fanget(self.entries-1)):
            yield buffer(self.shalist, i*20, 20)

    def __len__(self):
        return int(self._fanget(self.entries-1))


_mpi_count = 0
class PackIdxList:
    def __init__(self, dir):
        global _mpi_count
        assert(_mpi_count == 0) # these things suck tons of VM; don't waste it
        _mpi_count += 1
        self.dir = dir
        self.also = {}
        self.packs = []
        self.refresh()

    def __del__(self):
        global _mpi_count
        _mpi_count -= 1
        assert(_mpi_count == 0)

    def __iter__(self):
        return iter(idxmerge(self.packs))

    def __len__(self):
        return sum(len(pack) for pack in self.packs)

    def exists(self, hash):
        """Return nonempty if the object exists in the index files."""
        global _total_searches
        _total_searches += 1
        if hash in self.also:
            return True
        for i in range(len(self.packs)):
            p = self.packs[i]
            _total_searches -= 1  # will be incremented by sub-pack
            if p.exists(hash):
                # reorder so most recently used packs are searched first
                self.packs = [p] + self.packs[:i] + self.packs[i+1:]
                return p.name
        return None

    def refresh(self, skip_midx = False):
        """Refresh the index list.
        This method verifies if .midx files were superseded (e.g. all of its
        contents are in another, bigger .midx file) and removes the superseded
        files.

        If skip_midx is True, all work on .midx files will be skipped and .midx
        files will be removed from the list.

        The module-global variable 'ignore_midx' can force this function to
        always act as if skip_midx was True.
        """
        skip_midx = skip_midx or ignore_midx
        d = dict((p.name, p) for p in self.packs
                 if not skip_midx or not isinstance(p, PackMidx))
        if os.path.exists(self.dir):
            if not skip_midx:
                midxl = []
                for ix in self.packs:
                    if isinstance(ix, PackMidx):
                        for name in ix.idxnames:
                            d[os.path.join(self.dir, name)] = ix
                for f in os.listdir(self.dir):
                    full = os.path.join(self.dir, f)
                    if f.endswith('.midx') and not d.get(full):
                        mx = PackMidx(full)
                        (mxd, mxf) = os.path.split(mx.name)
                        broken = 0
                        for n in mx.idxnames:
                            if not os.path.exists(os.path.join(mxd, n)):
                                log(('warning: index %s missing\n' +
                                    '  used by %s\n') % (n, mxf))
                                broken += 1
                        if not broken:
                            midxl.append(mx)
                midxl.sort(lambda x,y: -cmp(len(x),len(y)))
                for ix in midxl:
                    any = 0
                    for sub in ix.idxnames:
                        found = d.get(os.path.join(self.dir, sub))
                        if not found or isinstance(found, PackIdx):
                            # doesn't exist, or exists but not in a midx
                            d[ix.name] = ix
                            for name in ix.idxnames:
                                d[os.path.join(self.dir, name)] = ix
                            any += 1
                            break
                    if not any and not ix.force_keep:
                        debug1('midx: removing redundant: %s\n'
                               % os.path.basename(ix.name))
                        unlink(ix.name)
            for f in os.listdir(self.dir):
                full = os.path.join(self.dir, f)
                if f.endswith('.idx') and not d.get(full):
                    ix = PackIdx(full)
                    d[full] = ix
            self.packs = list(set(d.values()))
        debug1('PackIdxList: using %d index%s.\n'
            % (len(self.packs), len(self.packs)!=1 and 'es' or ''))

    def add(self, hash):
        """Insert an additional object in the list."""
        self.also[hash] = 1

    def zap_also(self):
        """Remove all additional objects from the list."""
        self.also = {}


def calc_hash(type, content):
    """Calculate some content's hash in the Git fashion."""
    header = '%s %d\0' % (type, len(content))
    sum = Sha1(header)
    sum.update(content)
    return sum.digest()


def _shalist_sort_key(ent):
    (mode, name, id) = ent
    if stat.S_ISDIR(int(mode, 8)):
        return name + '/'
    else:
        return name


def open_idx(filename):
    if filename.endswith('.idx'):
        return PackIdx(filename)
    elif filename.endswith('.midx'):
        return PackMidx(filename)
    else:
        raise GitError('idx filenames must end with .idx or .midx')


def idxmerge(idxlist, final_progress=True):
    """Generate a list of all the objects reachable in a PackIdxList."""
    total = sum(len(i) for i in idxlist)
    iters = (iter(i) for i in idxlist)
    heap = [(next(it), it) for it in iters]
    heapq.heapify(heap)
    count = 0
    last = None
    while heap:
        if (count % 10024) == 0:
            progress('Reading indexes: %.2f%% (%d/%d)\r'
                     % (count*100.0/total, count, total))
        (e, it) = heap[0]
        if e != last:
            yield e
            last = e
        count += 1
        e = next(it)
        if e:
            heapq.heapreplace(heap, (e, it))
        else:
            heapq.heappop(heap)
    if final_progress:
        log('Reading indexes: %.2f%% (%d/%d), done.\n' % (100, total, total))


class PackWriter:
    """Writes Git objects insid a pack file."""
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
        if self.objcache == None:
            if self.objcache_maker:
                self.objcache = self.objcache_maker()
            else:
                self.objcache = PackIdxList(repo('objects/pack'))

    def _open(self):
        if not self.file:
            self._make_objcache()
            (fd,name) = tempfile.mkstemp(suffix='.pack', dir=repo('objects'))
            self.file = os.fdopen(fd, 'w+b')
            assert(name.endswith('.pack'))
            self.filename = name[:-5]
            self.file.write('PACK\0\0\0\2\0\0\0\0')

    def _raw_write(self, datalist):
        self._open()
        f = self.file
        # in case we get interrupted (eg. KeyboardInterrupt), it's best if
        # the file never has a *partial* blob.  So let's make sure it's
        # all-or-nothing.  (The blob shouldn't be very big anyway, thanks
        # to our hashsplit algorithm.)  f.write() does its own buffering,
        # but that's okay because we'll flush it in _end().
        oneblob = ''.join(datalist)
        f.write(oneblob)
        self.outbytes += len(oneblob)
        self.count += 1

    def _write(self, bin, type, content):
        if verbose:
            log('>')
        self._raw_write(_encode_packobj(type, content))
        return bin

    def breakpoint(self):
        """Clear byte and object counts and return the last processed id."""
        id = self._end()
        self.outbytes = self.count = 0
        return id

    def write(self, type, content):
        """Write an object in this pack file."""
        return self._write(calc_hash(type, content), type, content)

    def exists(self, id):
        """Return non-empty if an object is found in the object cache."""
        if not self.objcache:
            self._make_objcache()
        return self.objcache.exists(id)

    def maybe_write(self, type, content):
        """Write an object to the pack file if not present and return its id."""
        bin = calc_hash(type, content)
        if not self.exists(bin):
            self._write(bin, type, content)
            self.objcache.add(bin)
        return bin

    def new_blob(self, blob):
        """Create a blob object in the pack with the supplied content."""
        return self.maybe_write('blob', blob)

    def new_tree(self, shalist):
        """Create a tree object in the pack."""
        shalist = sorted(shalist, key = _shalist_sort_key)
        l = []
        for (mode,name,bin) in shalist:
            assert(mode)
            assert(mode != '0')
            assert(mode[0] != '0')
            assert(name)
            assert(len(bin) == 20)
            l.append('%s %s\0%s' % (mode,name,bin))
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

    def new_commit(self, parent, tree, date, msg):
        """Create a commit object in the pack."""
        userline = '%s <%s@%s>' % (userfullname(), username(), hostname())
        commit = self._new_commit(tree, parent,
                                  userline, date, userline, date,
                                  msg)
        return commit

    def abort(self):
        """Remove the pack file from disk."""
        f = self.file
        if f:
            self.file = None
            f.close()
            os.unlink(self.filename + '.pack')

    def _end(self):
        f = self.file
        if not f: return None
        self.file = None
        self.objcache = None

        # update object count
        f.seek(8)
        cp = struct.pack('!i', self.count)
        assert(len(cp) == 4)
        f.write(cp)

        # calculate the pack sha1sum
        f.seek(0)
        sum = Sha1()
        while 1:
            b = f.read(65536)
            sum.update(b)
            if not b: break
        f.write(sum.digest())

        f.close()

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
        if os.path.exists(self.filename + '.map'):
            os.unlink(self.filename + '.map')
        os.rename(self.filename + '.pack', nameprefix + '.pack')
        os.rename(self.filename + '.idx', nameprefix + '.idx')

        auto_midx(repo('objects/pack'))
        return nameprefix

    def close(self):
        """Close the pack file and move it to its definitive path."""
        return self._end()


def _git_date(date):
    return '%d %s' % (date, time.strftime('%z', time.localtime(date)))


def _gitenv():
    os.environ['GIT_DIR'] = os.path.abspath(repo())


def list_refs(refname = None):
    """Generate a list of tuples in the form (refname,hash).
    If a ref name is specified, list only this particular ref.
    """
    argv = ['git', 'show-ref', '--']
    if refname:
        argv += [refname]
    p = subprocess.Popen(argv, preexec_fn = _gitenv, stdout = subprocess.PIPE)
    out = p.stdout.read().strip()
    rv = p.wait()  # not fatal
    if rv:
        assert(not out)
    if out:
        for d in out.split('\n'):
            (sha, name) = d.split(' ', 1)
            yield (name, sha.decode('hex'))


def read_ref(refname):
    """Get the commit id of the most recent commit made on a given ref."""
    l = list(list_refs(refname))
    if l:
        assert(len(l) == 1)
        return l[0][1]
    else:
        return None


def rev_list(ref, count=None):
    """Generate a list of reachable commits in reverse chronological order.

    This generator walks through commits, from child to parent, that are
    reachable via the specified ref and yields a series of tuples of the form
    (date,hash).

    If count is a non-zero integer, limit the number of commits to "count"
    objects.
    """
    assert(not ref.startswith('-'))
    opts = []
    if count:
        opts += ['-n', str(atoi(count))]
    argv = ['git', 'rev-list', '--pretty=format:%ct'] + opts + [ref, '--']
    p = subprocess.Popen(argv, preexec_fn = _gitenv, stdout = subprocess.PIPE)
    commit = None
    for row in p.stdout:
        s = row.strip()
        if s.startswith('commit '):
            commit = s[7:].decode('hex')
        else:
            date = int(s)
            yield (date, commit)
    rv = p.wait()  # not fatal
    if rv:
        raise GitError, 'git rev-list returned error %d' % rv


def rev_get_date(ref):
    """Get the date of the latest commit on the specified ref."""
    for (date, commit) in rev_list(ref, count=1):
        return date
    raise GitError, 'no such commit %r' % ref


def update_ref(refname, newval, oldval):
    """Change the commit pointed to by a branch."""
    if not oldval:
        oldval = ''
    assert(refname.startswith('refs/heads/'))
    p = subprocess.Popen(['git', 'update-ref', refname,
                          newval.encode('hex'), oldval.encode('hex')],
                         preexec_fn = _gitenv)
    _git_wait('git update-ref', p)


def guess_repo(path=None):
    """Set the path value in the global variable "repodir".
    This makes bup look for an existing bup repository, but not fail if a
    repository doesn't exist. Usually, if you are interacting with a bup
    repository, you would not be calling this function but using
    check_repo_or_die().
    """
    global repodir
    if path:
        repodir = path
    if not repodir:
        repodir = os.environ.get('BUP_DIR')
        if not repodir:
            repodir = os.path.expanduser('~/.bup')


def init_repo(path=None):
    """Create the Git bare repository for bup in a given path."""
    guess_repo(path)
    d = repo()
    if os.path.exists(d) and not os.path.isdir(os.path.join(d, '.')):
        raise GitError('"%d" exists but is not a directory\n' % d)
    p = subprocess.Popen(['git', '--bare', 'init'], stdout=sys.stderr,
                         preexec_fn = _gitenv)
    _git_wait('git init', p)
    # Force the index version configuration in order to ensure bup works
    # regardless of the version of the installed Git binary.
    p = subprocess.Popen(['git', 'config', 'pack.indexVersion', '2'],
                         stdout=sys.stderr, preexec_fn = _gitenv)
    _git_wait('git config', p)


def check_repo_or_die(path=None):
    """Make sure a bup repository exists, and abort if not.
    If the path to a particular repository was not specified, this function
    initializes the default repository automatically.
    """
    guess_repo(path)
    if not os.path.isdir(repo('objects/pack/.')):
        if repodir == home_repodir:
            init_repo()
        else:
            log('error: %r is not a bup/git repository\n' % repo())
            sys.exit(15)


def treeparse(buf):
    """Generate a list of (mode, name, hash) tuples of objects from 'buf'."""
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
    """Get Git's version and ensure a usable version is installed.

    The returned version is formatted as an ordered tuple with each position
    representing a digit in the version tag. For example, the following tuple
    would represent version 1.6.6.9:

        ('1', '6', '6', '9')
    """
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
    needed = ('1','5', '3', '1')
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


class _AbortableIter:
    def __init__(self, it, onabort = None):
        self.it = it
        self.onabort = onabort
        self.done = None

    def __iter__(self):
        return self

    def next(self):
        try:
            return self.it.next()
        except StopIteration, e:
            self.done = True
            raise
        except:
            self.abort()
            raise

    def abort(self):
        """Abort iteration and call the abortion callback, if needed."""
        if not self.done:
            self.done = True
            if self.onabort:
                self.onabort()

    def __del__(self):
        self.abort()


_ver_warned = 0
class CatPipe:
    """Link to 'git cat-file' that is used to retrieve blob data."""
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
            self.p = self.inprogress = None
            self.get = self._fast_get

    def _abort(self):
        if self.p:
            self.p.stdout.close()
            self.p.stdin.close()
        self.p = None
        self.inprogress = None

    def _restart(self):
        self._abort()
        self.p = subprocess.Popen(['git', 'cat-file', '--batch'],
                                  stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  close_fds = True,
                                  preexec_fn = _gitenv)

    def _fast_get(self, id):
        if not self.p or self.p.poll() != None:
            self._restart()
        assert(self.p)
        assert(self.p.poll() == None)
        if self.inprogress:
            log('_fast_get: opening %r while %r is open'
                % (id, self.inprogress))
        assert(not self.inprogress)
        assert(id.find('\n') < 0)
        assert(id.find('\r') < 0)
        assert(id[0] != '-')
        self.inprogress = id
        self.p.stdin.write('%s\n' % id)
        hdr = self.p.stdout.readline()
        if hdr.endswith(' missing\n'):
            raise KeyError('blob %r is missing' % id)
        spl = hdr.split(' ')
        if len(spl) != 3 or len(spl[0]) != 40:
            raise GitError('expected blob, got %r' % spl)
        (hex, type, size) = spl

        it = _AbortableIter(chunkyreader(self.p.stdout, int(spl[2])),
                           onabort = self._abort)
        try:
            yield type
            for blob in it:
                yield blob
            assert(self.p.stdout.readline() == '\n')
            self.inprogress = None
        except Exception, e:
            it.abort()
            raise

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
            for (mode, name, sha) in treeparse(treefile):
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
        """Generate a list of the content of all blobs that can be reached
        from an object.  The hash given in 'id' must point to a blob, a tree
        or a commit. The content of all blobs that can be seen from trees or
        commits will be added to the list.
        """
        try:
            for d in self._join(self.get(id)):
                yield d
        except StopIteration:
            log('booger!\n')
