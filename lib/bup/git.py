"""Git interaction library.
bup repositories are in Git format. This library allows us to
interact with the Git data structures.
"""
import os, sys, zlib, time, subprocess, struct, stat, re, tempfile, glob
from bup.helpers import *
from bup import _helpers, path, midx, bloom, xstat

max_pack_size = 1000*1000*1000  # larger packs will slow down pruning
max_pack_objects = 200*1000  # cache memory usage is about 83 bytes per object
SEEK_END=2  # os.SEEK_END is not defined in python 2.4

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


def shorten_hash(s):
    return re.sub(r'([^0-9a-z]|\b)([0-9a-z]{7})[0-9a-z]{33}([^0-9a-z]|\b)',
                  r'\1\2*\3', s)


def repo_rel(path):
    full = os.path.abspath(path)
    fullrepo = os.path.abspath(repo(''))
    if not fullrepo.endswith('/'):
        fullrepo += '/'
    if full.startswith(fullrepo):
        path = full[len(fullrepo):]
    if path.startswith('index-cache/'):
        path = path[len('index-cache/'):]
    return shorten_hash(path)


def all_packdirs():
    paths = [repo('objects/pack')]
    paths += glob.glob(repo('index-cache/*/.'))
    return paths


def auto_midx(objdir):
    args = [path.exe(), 'midx', '--auto', '--dir', objdir]
    try:
        rv = subprocess.call(args, stdout=open('/dev/null', 'w'))
    except OSError, e:
        # make sure 'args' gets printed to help with debugging
        add_error('%r: exception: %s' % (args, e))
        raise
    if rv:
        add_error('%r: returned %d' % (args, rv))

    args = [path.exe(), 'bloom', '--dir', objdir]
    try:
        rv = subprocess.call(args, stdout=open('/dev/null', 'w'))
    except OSError, e:
        # make sure 'args' gets printed to help with debugging
        add_error('%r: exception: %s' % (args, e))
        raise
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


def calc_hash(type, content):
    """Calculate some content's hash in the Git fashion."""
    header = '%s %d\0' % (type, len(content))
    sum = Sha1(header)
    sum.update(content)
    return sum.digest()


def _shalist_sort_key(ent):
    (mode, name, id) = ent
    assert(mode+0 == mode)
    if stat.S_ISDIR(mode):
        return name + '/'
    else:
        return name


def tree_encode(shalist):
    """Generate a git tree object from (mode,name,hash) tuples."""
    shalist = sorted(shalist, key = _shalist_sort_key)
    l = []
    for (mode,name,bin) in shalist:
        assert(mode)
        assert(mode+0 == mode)
        assert(name)
        assert(len(bin) == 20)
        s = '%o %s\0%s' % (mode,name,bin)
        assert(s[0] != '0')  # 0-padded octal is not acceptable in a git tree
        l.append(s)
    return ''.join(l)


def tree_decode(buf):
    """Generate a list of (mode,name,hash) from the git tree object in buf."""
    ofs = 0
    while ofs < len(buf):
        z = buf[ofs:].find('\0')
        assert(z > 0)
        spl = buf[ofs:ofs+z].split(' ', 1)
        assert(len(spl) == 2)
        mode,name = spl
        sha = buf[ofs+z+1:ofs+z+1+20]
        ofs += z+1+20
        yield (int(mode, 8), name, sha)


def _encode_packobj(type, content, compression_level=1):
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
    if compression_level > 9:
        compression_level = 9
    elif compression_level < 0:
        compression_level = 0
    z = zlib.compressobj(compression_level)
    yield szout
    yield z.compress(content)
    yield z.flush()


def _encode_looseobj(type, content, compression_level=1):
    z = zlib.compressobj(compression_level)
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
    def __init__(self):
        assert(0)

    def find_offset(self, hash):
        """Get the offset of an object inside the index file."""
        idx = self._idx_from_hash(hash)
        if idx != None:
            return self._ofs_from_idx(idx)
        return None

    def exists(self, hash, want_source=False):
        """Return nonempty if the object exists in this index."""
        if hash and (self._idx_from_hash(hash) != None):
            return want_source and os.path.basename(self.name) or True
        return None

    def __len__(self):
        return int(self.fanout[255])

    def _idx_from_hash(self, hash):
        global _total_searches, _total_steps
        _total_searches += 1
        assert(len(hash) == 20)
        b1 = ord(hash[0])
        start = self.fanout[b1-1] # range -1..254
        end = self.fanout[b1] # range 0..255
        want = str(hash)
        _total_steps += 1  # lookup table is a step
        while start < end:
            _total_steps += 1
            mid = start + (end-start)/2
            v = self._idx_to_hash(mid)
            if v < want:
                start = mid+1
            elif v > want:
                end = mid
            else: # got it!
                return mid
        return None


class PackIdxV1(PackIdx):
    """Object representation of a Git pack index (version 1) file."""
    def __init__(self, filename, f):
        self.name = filename
        self.idxnames = [self.name]
        self.map = mmap_read(f)
        self.fanout = list(struct.unpack('!256I',
                                         str(buffer(self.map, 0, 256*4))))
        self.fanout.append(0)  # entry "-1"
        nsha = self.fanout[255]
        self.sha_ofs = 256*4
        self.shatable = buffer(self.map, self.sha_ofs, nsha*24)

    def _ofs_from_idx(self, idx):
        return struct.unpack('!I', str(self.shatable[idx*24 : idx*24+4]))[0]

    def _idx_to_hash(self, idx):
        return str(self.shatable[idx*24+4 : idx*24+24])

    def __iter__(self):
        for i in xrange(self.fanout[255]):
            yield buffer(self.map, 256*4 + 24*i + 4, 20)


class PackIdxV2(PackIdx):
    """Object representation of a Git pack index (version 2) file."""
    def __init__(self, filename, f):
        self.name = filename
        self.idxnames = [self.name]
        self.map = mmap_read(f)
        assert(str(self.map[0:8]) == '\377tOc\0\0\0\2')
        self.fanout = list(struct.unpack('!256I',
                                         str(buffer(self.map, 8, 256*4))))
        self.fanout.append(0)  # entry "-1"
        nsha = self.fanout[255]
        self.sha_ofs = 8 + 256*4
        self.shatable = buffer(self.map, self.sha_ofs, nsha*20)
        self.ofstable = buffer(self.map,
                               self.sha_ofs + nsha*20 + nsha*4,
                               nsha*4)
        self.ofs64table = buffer(self.map,
                                 8 + 256*4 + nsha*20 + nsha*4 + nsha*4)

    def _ofs_from_idx(self, idx):
        ofs = struct.unpack('!I', str(buffer(self.ofstable, idx*4, 4)))[0]
        if ofs & 0x80000000:
            idx64 = ofs & 0x7fffffff
            ofs = struct.unpack('!Q',
                                str(buffer(self.ofs64table, idx64*8, 8)))[0]
        return ofs

    def _idx_to_hash(self, idx):
        return str(self.shatable[idx*20:(idx+1)*20])

    def __iter__(self):
        for i in xrange(self.fanout[255]):
            yield buffer(self.map, 8 + 256*4 + 20*i, 20)


_mpi_count = 0
class PackIdxList:
    def __init__(self, dir):
        global _mpi_count
        assert(_mpi_count == 0) # these things suck tons of VM; don't waste it
        _mpi_count += 1
        self.dir = dir
        self.also = set()
        self.packs = []
        self.do_bloom = False
        self.bloom = None
        self.refresh()

    def __del__(self):
        global _mpi_count
        _mpi_count -= 1
        assert(_mpi_count == 0)

    def __iter__(self):
        return iter(idxmerge(self.packs))

    def __len__(self):
        return sum(len(pack) for pack in self.packs)

    def exists(self, hash, want_source=False):
        """Return nonempty if the object exists in the index files."""
        global _total_searches
        _total_searches += 1
        if hash in self.also:
            return True
        if self.do_bloom and self.bloom:
            if self.bloom.exists(hash):
                self.do_bloom = False
            else:
                _total_searches -= 1  # was counted by bloom
                return None
        for i in xrange(len(self.packs)):
            p = self.packs[i]
            _total_searches -= 1  # will be incremented by sub-pack
            ix = p.exists(hash, want_source=want_source)
            if ix:
                # reorder so most recently used packs are searched first
                self.packs = [p] + self.packs[:i] + self.packs[i+1:]
                return ix
        self.do_bloom = True
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
        self.bloom = None # Always reopen the bloom as it may have been relaced
        self.do_bloom = False
        skip_midx = skip_midx or ignore_midx
        d = dict((p.name, p) for p in self.packs
                 if not skip_midx or not isinstance(p, midx.PackMidx))
        if os.path.exists(self.dir):
            if not skip_midx:
                midxl = []
                for ix in self.packs:
                    if isinstance(ix, midx.PackMidx):
                        for name in ix.idxnames:
                            d[os.path.join(self.dir, name)] = ix
                for full in glob.glob(os.path.join(self.dir,'*.midx')):
                    if not d.get(full):
                        mx = midx.PackMidx(full)
                        (mxd, mxf) = os.path.split(mx.name)
                        broken = False
                        for n in mx.idxnames:
                            if not os.path.exists(os.path.join(mxd, n)):
                                log(('warning: index %s missing\n' +
                                    '  used by %s\n') % (n, mxf))
                                broken = True
                        if broken:
                            del mx
                            unlink(full)
                        else:
                            midxl.append(mx)
                midxl.sort(key=lambda ix:
                           (-len(ix), -xstat.stat(ix.name).st_mtime))
                for ix in midxl:
                    any_needed = False
                    for sub in ix.idxnames:
                        found = d.get(os.path.join(self.dir, sub))
                        if not found or isinstance(found, PackIdx):
                            # doesn't exist, or exists but not in a midx
                            any_needed = True
                            break
                    if any_needed:
                        d[ix.name] = ix
                        for name in ix.idxnames:
                            d[os.path.join(self.dir, name)] = ix
                    elif not ix.force_keep:
                        debug1('midx: removing redundant: %s\n'
                               % os.path.basename(ix.name))
                        unlink(ix.name)
            for full in glob.glob(os.path.join(self.dir,'*.idx')):
                if not d.get(full):
                    try:
                        ix = open_idx(full)
                    except GitError, e:
                        add_error(e)
                        continue
                    d[full] = ix
            bfull = os.path.join(self.dir, 'bup.bloom')
            if self.bloom is None and os.path.exists(bfull):
                self.bloom = bloom.ShaBloom(bfull)
            self.packs = list(set(d.values()))
            self.packs.sort(lambda x,y: -cmp(len(x),len(y)))
            if self.bloom and self.bloom.valid() and len(self.bloom) >= len(self):
                self.do_bloom = True
            else:
                self.bloom = None
        debug1('PackIdxList: using %d index%s.\n'
            % (len(self.packs), len(self.packs)!=1 and 'es' or ''))

    def add(self, hash):
        """Insert an additional object in the list."""
        self.also.add(hash)


def open_idx(filename):
    if filename.endswith('.idx'):
        f = open(filename, 'rb')
        header = f.read(8)
        if header[0:4] == '\377tOc':
            version = struct.unpack('!I', header[4:8])[0]
            if version == 2:
                return PackIdxV2(filename, f)
            else:
                raise GitError('%s: expected idx file version 2, got %d'
                               % (filename, version))
        elif len(header) == 8 and header[0:4] < '\377tOc':
            return PackIdxV1(filename, f)
        else:
            raise GitError('%s: unrecognized idx file header' % filename)
    elif filename.endswith('.midx'):
        return midx.PackMidx(filename)
    else:
        raise GitError('idx filenames must end with .idx or .midx')


def idxmerge(idxlist, final_progress=True):
    """Generate a list of all the objects reachable in a PackIdxList."""
    def pfunc(count, total):
        qprogress('Reading indexes: %.2f%% (%d/%d)\r'
                  % (count*100.0/total, count, total))
    def pfinal(count, total):
        if final_progress:
            progress('Reading indexes: %.2f%% (%d/%d), done.\n'
                     % (100, total, total))
    return merge_iter(idxlist, 10024, pfunc, pfinal)


def _make_objcache():
    return PackIdxList(repo('objects/pack'))

class PackWriter:
    """Writes Git objects inside a pack file."""
    def __init__(self, objcache_maker=_make_objcache, compression_level=1):
        self.count = 0
        self.outbytes = 0
        self.filename = None
        self.file = None
        self.idx = None
        self.objcache_maker = objcache_maker
        self.objcache = None
        self.compression_level = compression_level

    def __del__(self):
        self.close()

    def _open(self):
        if not self.file:
            (fd,name) = tempfile.mkstemp(suffix='.pack', dir=repo('objects'))
            self.file = os.fdopen(fd, 'w+b')
            assert(name.endswith('.pack'))
            self.filename = name[:-5]
            self.file.write('PACK\0\0\0\2\0\0\0\0')
            self.idx = list(list() for i in xrange(256))

    def _raw_write(self, datalist, sha):
        self._open()
        f = self.file
        # in case we get interrupted (eg. KeyboardInterrupt), it's best if
        # the file never has a *partial* blob.  So let's make sure it's
        # all-or-nothing.  (The blob shouldn't be very big anyway, thanks
        # to our hashsplit algorithm.)  f.write() does its own buffering,
        # but that's okay because we'll flush it in _end().
        oneblob = ''.join(datalist)
        try:
            f.write(oneblob)
        except IOError, e:
            raise GitError, e, sys.exc_info()[2]
        nw = len(oneblob)
        crc = zlib.crc32(oneblob) & 0xffffffff
        self._update_idx(sha, crc, nw)
        self.outbytes += nw
        self.count += 1
        return nw, crc

    def _update_idx(self, sha, crc, size):
        assert(sha)
        if self.idx:
            self.idx[ord(sha[0])].append((sha, crc, self.file.tell() - size))

    def _write(self, sha, type, content):
        if verbose:
            log('>')
        if not sha:
            sha = calc_hash(type, content)
        size, crc = self._raw_write(_encode_packobj(type, content,
                                                    self.compression_level),
                                    sha=sha)
        if self.outbytes >= max_pack_size or self.count >= max_pack_objects:
            self.breakpoint()
        return sha

    def breakpoint(self):
        """Clear byte and object counts and return the last processed id."""
        id = self._end()
        self.outbytes = self.count = 0
        return id

    def _require_objcache(self):
        if self.objcache is None and self.objcache_maker:
            self.objcache = self.objcache_maker()
        if self.objcache is None:
            raise GitError(
                    "PackWriter not opened or can't check exists w/o objcache")

    def exists(self, id, want_source=False):
        """Return non-empty if an object is found in the object cache."""
        self._require_objcache()
        return self.objcache.exists(id, want_source=want_source)

    def maybe_write(self, type, content):
        """Write an object to the pack file if not present and return its id."""
        sha = calc_hash(type, content)
        if not self.exists(sha):
            self._write(sha, type, content)
            self._require_objcache()
            self.objcache.add(sha)
        return sha

    def new_blob(self, blob):
        """Create a blob object in the pack with the supplied content."""
        return self.maybe_write('blob', blob)

    def new_tree(self, shalist):
        """Create a tree object in the pack."""
        content = tree_encode(shalist)
        return self.maybe_write('tree', content)

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
            self.idx = None
            self.file = None
            f.close()
            os.unlink(self.filename + '.pack')

    def _end(self, run_midx=True):
        f = self.file
        if not f: return None
        self.file = None
        self.objcache = None
        idx = self.idx
        self.idx = None

        # update object count
        f.seek(8)
        cp = struct.pack('!i', self.count)
        assert(len(cp) == 4)
        f.write(cp)

        # calculate the pack sha1sum
        f.seek(0)
        sum = Sha1()
        for b in chunkyreader(f):
            sum.update(b)
        packbin = sum.digest()
        f.write(packbin)
        f.close()

        obj_list_sha = self._write_pack_idx_v2(self.filename + '.idx', idx, packbin)

        nameprefix = repo('objects/pack/pack-%s' % obj_list_sha)
        if os.path.exists(self.filename + '.map'):
            os.unlink(self.filename + '.map')
        os.rename(self.filename + '.pack', nameprefix + '.pack')
        os.rename(self.filename + '.idx', nameprefix + '.idx')

        if run_midx:
            auto_midx(repo('objects/pack'))
        return nameprefix

    def close(self, run_midx=True):
        """Close the pack file and move it to its definitive path."""
        return self._end(run_midx=run_midx)

    def _write_pack_idx_v2(self, filename, idx, packbin):
        idx_f = open(filename, 'w+b')
        idx_f.write('\377tOc\0\0\0\2')

        ofs64_ofs = 8 + 4*256 + 28*self.count
        idx_f.truncate(ofs64_ofs)
        idx_f.seek(0)
        idx_map = mmap_readwrite(idx_f, close=False)
        idx_f.seek(0, SEEK_END)
        count = _helpers.write_idx(idx_f, idx_map, idx, self.count)
        assert(count == self.count)
        idx_map.close()
        idx_f.write(packbin)

        idx_f.seek(0)
        idx_sum = Sha1()
        b = idx_f.read(8 + 4*256)
        idx_sum.update(b)

        obj_list_sum = Sha1()
        for b in chunkyreader(idx_f, 20*self.count):
            idx_sum.update(b)
            obj_list_sum.update(b)
        namebase = obj_list_sum.hexdigest()

        for b in chunkyreader(idx_f):
            idx_sum.update(b)
        idx_f.write(idx_sum.digest())
        idx_f.close()

        return namebase


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


def rev_parse(committish):
    """Resolve the full hash for 'committish', if it exists.

    Should be roughly equivalent to 'git rev-parse'.

    Returns the hex value of the hash if it is found, None if 'committish' does
    not correspond to anything.
    """
    head = read_ref(committish)
    if head:
        debug2("resolved from ref: commit = %s\n" % head.encode('hex'))
        return head

    pL = PackIdxList(repo('objects/pack'))

    if len(committish) == 40:
        try:
            hash = committish.decode('hex')
        except TypeError:
            return None

        if pL.exists(hash):
            return hash

    return None


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
    d = repo()  # appends a / to the path
    parent = os.path.dirname(os.path.dirname(d))
    if parent and not os.path.exists(parent):
        raise GitError('parent directory "%s" does not exist\n' % parent)
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
    try:
        os.stat(repo('objects/pack/.'))
    except OSError, e:
        if e.errno == errno.ENOENT:
            if repodir != home_repodir:
                log('error: %r is not a bup repository; run "bup init"\n'
                    % repo())
                sys.exit(15)
            else:
                init_repo()
        else:
            log('error: %s\n' % e)
            sys.exit(14)


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
                                  bufsize = 4096,
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
        assert(not id.startswith('-'))
        self.inprogress = id
        self.p.stdin.write('%s\n' % id)
        self.p.stdin.flush()
        hdr = self.p.stdout.readline()
        if hdr.endswith(' missing\n'):
            self.inprogress = None
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
            for (mode, name, sha) in tree_decode(treefile):
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

def tags():
    """Return a dictionary of all tags in the form {hash: [tag_names, ...]}."""
    tags = {}
    for (n,c) in list_refs():
        if n.startswith('refs/tags/'):
            name = n[10:]
            if not c in tags:
                tags[c] = []

            tags[c].append(name)  # more than one tag can point at 'c'

    return tags
