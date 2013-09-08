#!/usr/bin/env python
import sys, time
from bup import hashsplit, git, options, client
from bup.helpers import *


optspec = """
bup split [-t] [-c] [-n name] OPTIONS [filenames...]
bup split -b OPTIONS [filenames...]
bup split <--noop [--copy]|--copy>  OPTIONS [filenames...]
--
 Modes:
b,blobs    output a series of blob ids.  Implies --fanout=0.
t,tree     output a tree id
c,commit   output a commit id
n,name=    save the result under the given name
noop       split the input, but throw away the result
copy       split the input, copy it to stdout, don't save to repo
 Options:
r,remote=  remote repository path
d,date=    date for the commit (seconds since the epoch)
q,quiet    don't print progress messages
v,verbose  increase log output (can be used more than once)
git-ids    read a list of git object ids from stdin and split their contents
keep-boundaries  don't let one chunk span two input files
bench      print benchmark timings to stderr
max-pack-size=  maximum bytes in a single pack
max-pack-objects=  maximum number of objects in a single pack
fanout=    average number of blobs in a single tree
bwlimit=   maximum bytes/sec to transmit to server
#,compress=  set compression level to # (0-9, 9 is highest) [1]
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

handle_ctrl_c()
git.check_repo_or_die()
if not (opt.blobs or opt.tree or opt.commit or opt.name or
        opt.noop or opt.copy):
    o.fatal("use one or more of -b, -t, -c, -n, --noop, --copy")
if (opt.noop or opt.copy) and (opt.blobs or opt.tree or
                               opt.commit or opt.name):
    o.fatal('--noop and --copy are incompatible with -b, -t, -c, -n')
if opt.blobs and (opt.tree or opt.commit or opt.name):
    o.fatal('-b is incompatible with -t, -c, -n')
if extra and opt.git_ids:
    o.fatal("don't provide filenames when using --git-ids")

if opt.verbose >= 2:
    git.verbose = opt.verbose - 1
    opt.bench = 1
if opt.max_pack_size:
    git.max_pack_size = parse_num(opt.max_pack_size)
if opt.max_pack_objects:
    git.max_pack_objects = parse_num(opt.max_pack_objects)
if opt.fanout:
    hashsplit.fanout = parse_num(opt.fanout)
if opt.blobs:
    hashsplit.fanout = 0
if opt.bwlimit:
    client.bwlimit = parse_num(opt.bwlimit)
if opt.date:
    date = parse_date_or_fatal(opt.date, o.fatal)
else:
    date = time.time()

total_bytes = 0
def prog(filenum, nbytes):
    global total_bytes
    total_bytes += nbytes
    if filenum > 0:
        qprogress('Splitting: file #%d, %d kbytes\r'
                  % (filenum+1, total_bytes/1024))
    else:
        qprogress('Splitting: %d kbytes\r' % (total_bytes/1024))


is_reverse = os.environ.get('BUP_SERVER_REVERSE')
if is_reverse and opt.remote:
    o.fatal("don't use -r in reverse mode; it's automatic")
start_time = time.time()

if opt.name and opt.name.startswith('.'):
    o.fatal("'%s' is not a valid branch name." % opt.name)
refname = opt.name and 'refs/heads/%s' % opt.name or None
if opt.noop or opt.copy:
    cli = pack_writer = oldref = None
elif opt.remote or is_reverse:
    cli = client.Client(opt.remote, compression_level=opt.compress)
    oldref = refname and cli.read_ref(refname) or None
    pack_writer = cli.new_packwriter()
else:
    cli = None
    oldref = refname and git.read_ref(refname) or None
    pack_writer = git.PackWriter(compression_level=opt.compress)

if opt.git_ids:
    # the input is actually a series of git object ids that we should retrieve
    # and split.
    #
    # This is a bit messy, but basically it converts from a series of
    # CatPipe.get() iterators into a series of file-type objects.
    # It would be less ugly if either CatPipe.get() returned a file-like object
    # (not very efficient), or split_to_shalist() expected an iterator instead
    # of a file.
    cp = git.CatPipe()
    class IterToFile:
        def __init__(self, it):
            self.it = iter(it)
        def read(self, size):
            v = next(self.it)
            return v or ''
    def read_ids():
        while 1:
            line = sys.stdin.readline()
            if not line:
                break
            if line:
                line = line.strip()
            try:
                it = cp.get(line.strip())
                next(it)  # skip the file type
            except KeyError, e:
                add_error('error: %s' % e)
                continue
            yield IterToFile(it)
    files = read_ids()
else:
    # the input either comes from a series of files or from stdin.
    files = extra and (open(fn) for fn in extra) or [sys.stdin]

if pack_writer and opt.blobs:
    shalist = hashsplit.split_to_blobs(pack_writer.new_blob, files,
                                       keep_boundaries=opt.keep_boundaries,
                                       progress=prog)
    for (sha, size, level) in shalist:
        print sha.encode('hex')
        reprogress()
elif pack_writer:  # tree or commit or name
    shalist = hashsplit.split_to_shalist(pack_writer.new_blob,
                                         pack_writer.new_tree,
                                         files,
                                         keep_boundaries=opt.keep_boundaries,
                                         progress=prog)
    tree = pack_writer.new_tree(shalist)
else:
    last = 0
    it = hashsplit.hashsplit_iter(files,
                                  keep_boundaries=opt.keep_boundaries,
                                  progress=prog)
    for (blob, level) in it:
        hashsplit.total_split += len(blob)
        if opt.copy:
            sys.stdout.write(str(blob))
        megs = hashsplit.total_split/1024/1024
        if not opt.quiet and last != megs:
            last = megs

if opt.verbose:
    log('\n')
if opt.tree:
    print tree.encode('hex')
if opt.commit or opt.name:
    msg = 'bup split\n\nGenerated by command:\n%r' % sys.argv
    ref = opt.name and ('refs/heads/%s' % opt.name) or None
    commit = pack_writer.new_commit(oldref, tree, date, msg)
    if opt.commit:
        print commit.encode('hex')

if pack_writer:
    pack_writer.close()  # must close before we can update the ref

if opt.name:
    if cli:
        cli.update_ref(refname, commit, oldref)
    else:
        git.update_ref(refname, commit, oldref)

if cli:
    cli.close()

secs = time.time() - start_time
size = hashsplit.total_split
if opt.bench:
    log('bup: %.2fkbytes in %.2f secs = %.2f kbytes/sec\n'
        % (size/1024., secs, size/1024./secs))

if saved_errors:
    log('WARNING: %d errors encountered while saving.\n' % len(saved_errors))
    sys.exit(1)
