
from __future__ import absolute_import, division, print_function
from binascii import hexlify
import sys, time

from bup import compat, hashsplit, git, options, client
from bup.compat import argv_bytes, environ, nullcontext
from bup.hashsplit import HashSplitter
from bup.helpers import (add_error, hostname, log, parse_num,
                         qprogress, reprogress, saved_errors,
                         valid_save_name,
                         parse_date_or_fatal)
from bup.io import byte_stream
from bup.pwdgrp import userfullname, username


optspec = """
bup split [-t] [-c] [-n name] OPTIONS [--git-ids | filenames...]
bup split -b OPTIONS [--git-ids | filenames...]
bup split --copy OPTIONS [--git-ids | filenames...]
bup split --noop [-b|-t] OPTIONS [--git-ids | filenames...]
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


class NoOpPackWriter:
    def __init__(self):
        self.closed = False
    def __enter__(self):
        return self
    def __exit__(self, type, value, traceback):
        self.close()
    def close(self):
        self.closed = True
    def __del__(self):
        assert self.closed
    def new_blob(self, content):
        return git.calc_hash(b'blob', content)
    def new_tree(self, shalist):
        return git.calc_hash(b'tree', git.tree_encode(shalist))

def opts_from_cmdline(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    opt.sources = extra

    if opt.name: opt.name = argv_bytes(opt.name)
    if opt.remote: opt.remote = argv_bytes(opt.remote)
    if opt.verbose is None: opt.verbose = 0

    if not (opt.blobs or opt.tree or opt.commit or opt.name or
            opt.noop or opt.copy):
        o.fatal("use one or more of -b, -t, -c, -n, --noop, --copy")
    if opt.copy and (opt.blobs or opt.tree):
        o.fatal('--copy is incompatible with -b, -t')
    if (opt.noop or opt.copy) and (opt.commit or opt.name):
        o.fatal('--noop and --copy are incompatible with -c, -n')
    if opt.blobs and (opt.tree or opt.commit or opt.name):
        o.fatal('-b is incompatible with -t, -c, -n')
    if extra and opt.git_ids:
        o.fatal("don't provide filenames when using --git-ids")
    if opt.verbose >= 2:
        git.verbose = opt.verbose - 1
        opt.bench = 1
    if opt.max_pack_size:
        opt.max_pack_size = parse_num(opt.max_pack_size)
    if opt.max_pack_objects:
        opt.max_pack_objects = parse_num(opt.max_pack_objects)
    if opt.fanout:
        opt.fanout = parse_num(opt.fanout)
    if opt.bwlimit:
        opt.bwlimit = parse_num(opt.bwlimit)
    if opt.date:
        opt.date = parse_date_or_fatal(opt.date, o.fatal)
    else:
        opt.date = time.time()

    opt.is_reverse = environ.get(b'BUP_SERVER_REVERSE')
    if opt.is_reverse:
        if opt.remote:
            o.fatal("don't use -r in reverse mode; it's automatic")
        if not opt.sources or opt.git_ids:
            o.fatal('"bup on ... split" does not support reading from standard input')

    if opt.name and not valid_save_name(opt.name):
        o.fatal("'%r' is not a valid branch name." % opt.name)

    return opt

def split(opt, files, parent, out, pack_writer):
    # Hack around lack of nonlocal vars in python 2
    total_bytes = [0]
    def prog(filenum, nbytes):
        total_bytes[0] += nbytes
        if filenum > 0:
            qprogress('Splitting: file #%d, %d kbytes\r'
                      % (filenum+1, total_bytes[0] // 1024))
        else:
            qprogress('Splitting: %d kbytes\r' % (total_bytes[0] // 1024))

    new_blob = pack_writer.new_blob
    new_tree = pack_writer.new_tree
    if opt.blobs:
        shalist = hashsplit.split_to_blobs(new_blob, files,
                                           keep_boundaries=opt.keep_boundaries,
                                           progress=prog)
        for sha, size, level in shalist:
            out.write(hexlify(sha) + b'\n')
            reprogress()
    elif opt.tree or opt.commit or opt.name:
        if opt.name: # insert dummy_name which may be used as a restore target
            mode, sha = \
                hashsplit.split_to_blob_or_tree(new_blob, new_tree, files,
                                                keep_boundaries=opt.keep_boundaries,
                                                progress=prog)
            splitfile_name = git.mangle_name(b'data', hashsplit.GIT_MODE_FILE, mode)
            shalist = [(mode, splitfile_name, sha)]
        else:
            shalist = \
                hashsplit.split_to_shalist(new_blob, new_tree, files,
                                           keep_boundaries=opt.keep_boundaries,
                                           progress=prog)
        tree = new_tree(shalist)
    else:
        last = 0
        for blob, level in HashSplitter(files, progress=prog,
                                        keep_boundaries=opt.keep_boundaries,
                                        bits=hashsplit.BUP_BLOBBITS,
                                        fanbits=hashsplit.fanbits()):
            hashsplit.total_split += len(blob)
            if opt.copy:
                sys.stdout.write(str(blob))
            megs = hashsplit.total_split // 1024 // 1024
            if not opt.quiet and last != megs:
                last = megs

    if opt.verbose:
        log('\n')
    if opt.tree:
        out.write(hexlify(tree) + b'\n')

    commit = None
    if opt.commit or opt.name:
        msg = b'bup split\n\nGenerated by command:\n%r\n' % compat.get_argvb()
        userline = b'%s <%s@%s>' % (userfullname(), username(), hostname())
        commit = pack_writer.new_commit(tree, parent, userline, opt.date,
                                        None, userline, opt.date, None, msg)
        if opt.commit:
            out.write(hexlify(commit) + b'\n')

    return commit

def main(argv):
    opt = opts_from_cmdline(argv)
    if opt.verbose >= 2:
        git.verbose = opt.verbose - 1
    if opt.fanout:
        hashsplit.fanout = opt.fanout
    if opt.blobs:
        hashsplit.fanout = 0
    if opt.bwlimit:
        client.bwlimit = opt.bwlimit

    start_time = time.time()

    sys.stdout.flush()
    out = byte_stream(sys.stdout)
    stdin = byte_stream(sys.stdin)

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
                v = next(self.it, None)
                return v or b''
        def read_ids():
            while 1:
                line = stdin.readline()
                if not line:
                    break
                if line:
                    line = line.strip()
                try:
                    it = cp.get(line.strip())
                    next(it, None)  # skip the file info
                except KeyError as e:
                    add_error('error: %s' % e)
                    continue
                yield IterToFile(it)
        files = read_ids()
    else:
        # the input either comes from a series of files or from stdin.
        if opt.sources:
            files = (open(argv_bytes(fn), 'rb') for fn in opt.sources)
        else:
            files = [stdin]

    writing = not (opt.noop or opt.copy)
    remote_dest = opt.remote or opt.is_reverse

    if writing:
        git.check_repo_or_die()

    if remote_dest and writing:
        remote = opt.remote
        if opt.is_reverse:
            remote = b'reverse://%s' % opt.is_reverse
        cli = repo = client.Client(remote)
    else:
        cli = nullcontext()
        repo = git

    # cli creation must be last nontrivial command in each if clause above
    with cli:
        if opt.name and writing:
            refname = opt.name and b'refs/heads/%s' % opt.name
            oldref = repo.read_ref(refname)
        else:
            refname = oldref = None

        if not writing:
            pack_writer = NoOpPackWriter()
        elif not remote_dest:
            pack_writer = git.PackWriter(compression_level=opt.compress,
                                         max_pack_size=opt.max_pack_size,
                                         max_pack_objects=opt.max_pack_objects)
        else:
            pack_writer = cli.new_packwriter(compression_level=opt.compress,
                                             max_pack_size=opt.max_pack_size,
                                             max_pack_objects=opt.max_pack_objects)

        # packwriter creation must be last command in each if clause above
        with pack_writer:
            commit = split(opt, files, oldref, out, pack_writer)

        # pack_writer must be closed before we can update the ref
        if refname:
            repo.update_ref(refname, commit, oldref)

    secs = time.time() - start_time
    size = hashsplit.total_split
    if opt.bench:
        log('bup: %.2f kbytes in %.2f secs = %.2f kbytes/sec\n'
            % (size / 1024, secs, size / 1024 / secs))

    if saved_errors:
        log('WARNING: %d errors encountered while saving.\n' % len(saved_errors))
        sys.exit(1)
