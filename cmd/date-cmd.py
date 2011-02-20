#!/usr/bin/env python
import sys, struct, glob, urllib2, re, errno
from bup import options, hashsplit, git
from bup.helpers import *

FIDX_VERSION=1
FIDX_ENTRY_LEN=20+2+2

optspec = """
bup date [options...] <baseurl>
--
i,indir=   directory to search for existing objects (default: same as outdir)
d,outdir=  directory to write output files to
o,outfile= filename to write output to (only if input is a single file)
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) != 1:
    o.fatal("exactly one input URL expected")
if opt.outfile and len(extra) != 1:
    o.fatal('--outfile only works with a single input filename')
if opt.outfile and opt.outdir:
    o.fatal('--outfile is incompatible with --outdir')
if not opt.outfile and not opt.outdir:
    o.fatal('you must provide one of --outdir or --outfile')
if not opt.indir:
    opt.indir = opt.outdir


def is_url(path):
    return '://' in path


def targets_from_file(s):
    if s.startswith('<'):
        # it's HTML; pick out the anchors
        targets = re.findall('<a[^>]href=["\']([^"\']*)["\']', s)
        targets = [urllib2.unquote(t) for t in targets]
        return targets
    else:
        # it's not HTML; assume it's a one-per-line list of filenames
        return [i.strip() for i in s.strip().split('\n')]


def write_hash(outf, sha, wantsize):
    # FIXME: this inefficiently opens/closes the file for every chunk
    name,ofs,size = hashes[sha]
    assert(size == wantsize)
    f = open(name)
    f.seek(ofs)
    for b in chunkyreader(f, size):
        outf.write(b)


def fetch_chunk(progfunc, outf, sha, baseurl, target, ofs, size):
    global downloaded
    progfunc()
    if baseurl.startswith('file://'):
        url = os.path.join(baseurl[7:], target[:-5])
        inf = open(url)
        inf.seek(ofs)
    else:
        # FIXME: apparently urllib2 is a poor choice because it disconnects
        # after every single request.  Lame.
        # FIXME: use multiple ranges rather than a separate request per
        # range.
        url = os.path.join(baseurl, urllib2.quote(target[:-5]))
        headers = dict(Range='bytes=%d-%d' % (ofs, ofs+size-1))
        req = urllib2.Request(url, headers=headers)
        inf = urllib2.urlopen(req)
    for b in chunkyreader(inf, size):
        downloaded += len(b)
        progfunc()
        outf.write(b)
    outf.flush()


class Fidx:
    def __init__(self, name):
        self.name = name
        f = open(name)
        content = mmap_read(f)
        assert(len(content) >= 16)
        assert(content[0:4] == 'FIDX')
        ver = struct.unpack('!I', content[4:8])[0]
        assert(ver == FIDX_VERSION)
        wantsum = content[-20:]
        self.filesum = Sha1(content[:-20]).digest()
        assert(self.filesum == wantsum)
        self.content = buffer(content, 8, len(content)-20)

    def __len__(self):
        return len(self.content)//FIDX_ENTRY_LEN

    def __iter__(self):
        content = self.content
        ofs = 0
        for i in xrange(len(self)):
            b = buffer(content, i*FIDX_ENTRY_LEN, FIDX_ENTRY_LEN)
            sha = str(b[:20])
            (size,level) = struct.unpack('!HH', b[20:])
            yield sha,ofs,size,level
            ofs += size


hashes = {}

# First, read in the cache
fidxnames = glob.glob(os.path.join(opt.indir, '*.fidx'))
count = 0
for name in fidxnames:
    count += 1
    progress('Reading cache: %d/%d (%d hashes) %s\r'
             % (count, len(fidxnames), len(hashes), os.path.basename(name)))
    infile_name = name[:-5]
    st_fidx = os.stat(name)
    try:
        st_real = os.stat(infile_name)
    except OSError, e:
        if e.errno != errno.ENOENT:
            add_error('%s: %s' % (infile_name, e))
        continue  # if the file doesn't exist, the fidx is useless
    if st_real.st_mtime > st_fidx.st_mtime:
        # fidx is outdated
        # FIXME: don't just ignore it, update it!
        # FIXME: mtime isn't reliable enough; maybe store the expected mtime
        #   *inside* the fidx?
        unlink(name)
        continue
    f = Fidx(name)
    ecount = 0
    for sha,ofs,size,level in f:
        ecount += 1
        if not (ecount % 1234):
            qprogress('Reading fidx: %d/%d (%d hashes) %s\r'
                      % (count, len(fidxnames), len(hashes),
                         os.path.basename(name)))
        hashes[sha] = (infile_name,ofs,size)
        ofs += size
progress('Reading fidx: %d/%d (%d hashes), done.\n'
          % (count, len(fidxnames), len(hashes)))


# Get the index
baseurl = extra[0]
progress('Downloading base: %s\r' % baseurl)
if baseurl.endswith('.fidx'):
    # the baseurl is a particular fidx, not a file list, so just use a file
    # list of one.
    targets = [os.path.basename(baseurl)]
    baseurl = os.path.dirname(baseurl)
    if not is_url(baseurl):
        baseurl = 'file://%s' % baseurl
elif is_url(baseurl):
    # it's an actual URL; download it
    try:
        f = urllib2.urlopen(baseurl)
    except urllib2.URLError, e:
        add_error('baseurl: %s: %s' % (baseurl, e.args))
        targets = []
    else:
        s = f.read()
        baseurl = f.url  # might have been HTTP Redirected; use new location
        targets = targets_from_file(s)
else:
    # it's not an URL; assume it's a filename
    dn = os.path.join(baseurl, '.')
    if os.path.exists(dn):
        # a directory
        targets = os.listdir(dn)
        if not baseurl.endswith('/'):
            baseurl += '/'
    elif os.path.exists(baseurl):
        # an index file
        targets = targets_from_file(open(baseurl).read())
        while baseurl.endswith('/'):
            baseurl = baseurl[:-1]
    else:
        add_error('baseurl: %s: does not exist' % baseurl)
        targets = []
    baseurl = 'file://%s' % baseurl
baseurl = os.path.dirname(baseurl)
targets = [i for i in targets if (i.endswith('.fidx')
                                  and not i.startswith('.'))]
progress('Downloading base: %s, done.\n' % baseurl)
debug1('targets: %r\n' % targets)
if not targets:
    add_error('No target names found in baseurl.\n')

tcount = 0
needed = 0
will_write = 0
remaining_targets = []
for target in targets:
    tcount += 1
    progress('Download fidx: %d/%d\r' % (tcount, len(targets)))
    assert('/' not in target)
    assert(target.endswith('.fidx'))
    assert(not target.startswith('.'))
    fidxname = os.path.join(opt.outdir, target)
    outname = fidxname[:-5]
    outf = open(fidxname + '.tmp', 'w')
    url = os.path.join(baseurl, urllib2.quote(target))
    try:
        urlf = urllib2.urlopen(url)
    except urllib2.URLError, e:
        add_error('target: %s: %s' % (url, e))
        continue
    for b in chunkyreader(urlf):
        outf.write(b)
    outf.close()
    f = Fidx(fidxname + '.tmp')
    if os.path.exists(fidxname) and os.path.exists(outname):
        fold = Fidx(fidxname)
        if fold.filesum == f.filesum:
            # files are identical!  nothing to do.
            del fold
            del f
            unlink(fidxname + '.tmp')
            continue
    for sha,ofs,size,level in f:
        if sha not in hashes:
            needed += size
        will_write += size
    remaining_targets.append(target)
progress('Download fidx: %d/%d, done.\r' % (tcount, len(targets)))

targets = remaining_targets

# FIXME: read existing contents of bupchunks so we can resume a previous run
chunkf_name = os.path.join(opt.outdir, 'bupchunks.tmp')
chunkf = open(chunkf_name, 'a+')
tcount = 0
downloaded = 0
for target in targets:
    tcount += 1
    fidxname = os.path.join(opt.outdir, target)
    request = None
    cofs = chunkf.tell()
    f = Fidx(fidxname + '.tmp')
    for sha,ofs,size,level in f:
        if not sha in hashes:
            def prog():
                s = ('Downloading %.2f%% (%d/%dk, %d/%d files)\r'
                     % (downloaded*100.0/needed,
                        downloaded/1024, needed/1024,
                        tcount, len(targets)))
                qprogress(s)
            if request:
                (oldtarget,oldofs,oldsize) = request
                if oldtarget==target and oldofs+oldsize==ofs:
                    request = (target,oldofs,oldsize+size)
                else:
                    fetch_chunk(prog, chunkf, sha, baseurl,
                                oldtarget, oldofs, oldsize)
                    request = (target,ofs,size)
            else:
                request = (target,ofs,size)
            hashes[sha] = (chunkf_name,cofs,size)
            cofs += size
        elif hashes[sha][0] == chunkf_name:
            # this chunk appears twice, so we have to count it twice, but
            # we don't want to *download* it twice
            downloaded += size
    if request:
        (oldtarget,oldofs,oldsize) = request
        fetch_chunk(prog, chunkf, sha, baseurl, oldtarget, oldofs, oldsize)
if needed:
    progress('Downloading %.2f%% (%d/%dk, %d/%d files), done.\n'
             % (downloaded*100.0/needed,
                downloaded/1024, needed/1024,
                tcount, len(targets)))

tcount = 0
written = 0
for target in targets:
    tcount += 1
    fidxname = os.path.join(opt.outdir, target)
    outname = fidxname[:-5]
    print outname
    outf = open(outname + '.tmp', 'w')
    f = Fidx(fidxname + '.tmp')
    for sha,ofs,size,level in f:
        assert(sha in hashes)
        qprogress('Writing %.2f%% (%d/%dk, %d/%d files)\r'
                 % (written*100.0/will_write,
                    written/1024, will_write/1024,
                    tcount, len(targets)))
        write_hash(outf, sha, size)
        written += size
    outf.close()
    # FIXME: check outfile final sha1
    os.rename(outname + '.tmp', outname)
    os.rename(fidxname + '.tmp', fidxname)
    os.utime(fidxname, None)  # validate it: we know it matches the outfile
unlink(chunkf_name)
if will_write:
    progress('Writing %.2f%% (%d/%dk, %d/%d files), done.\n'
             % (written*100.0/will_write,
                written/1024, will_write/1024,
                tcount, len(targets)))

if saved_errors:
    log('WARNING: %d errors encountered.\n' % len(saved_errors))
    sys.exit(1)
