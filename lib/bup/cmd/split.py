
from binascii import hexlify
from functools import partial
from os import environb as environ
import os, sys, time

from bup import compat, hashsplit, git, options, client
from bup.compat import argv_bytes
from bup.config import ConfigError, derive_repo_addr
from bup.hashsplit import \
    split_to_blob_or_tree, split_to_blobs, split_to_shalist
from bup.helpers import \
    (EXIT_FAILURE,
     add_error, hostname, log,
     nullcontext_if_not,
     parse_date_or_fatal,
     parse_num,
     qprogress,
     reprogress,
     valid_save_name)
from bup.io import byte_stream
from bup.pwdgrp import userfullname, username
from bup.repo import make_repo


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
#,compress=  set compression level to # (0-9, 9 is highest)
"""


def opts_from_cmdline(o, argv, reverse):
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

    if reverse and (not opt.sources or opt.git_ids):
        o.fatal('"bup on ... split" does not support reading from standard input')
    opt.repo = derive_repo_addr(remote=opt.remote, die=o.fatal)

    if opt.name and not valid_save_name(opt.name):
        o.fatal("'%r' is not a valid branch name." % opt.name)

    return opt


def split(opt, files, parent, out, split_cfg, *,
          new_blob, new_tree, new_commit=None):
    if opt.noop or opt.copy:
        assert not new_commit

    # Hack around lack of nonlocal vars in python 2
    total_bytes = [0]
    def prog(filenum, nbytes):
        total_bytes[0] += nbytes
        if filenum > 0:
            qprogress('Splitting: file #%d, %d kbytes\r'
                      % (filenum+1, total_bytes[0] // 1024))
        else:
            qprogress('Splitting: %d kbytes\r' % (total_bytes[0] // 1024))

    assert 'progress' not in split_cfg
    split_cfg['progress'] = prog
    if opt.blobs:
        shalist = \
            split_to_blobs(new_blob, hashsplit.from_config(files, split_cfg))
        for sha, size, level in shalist:
            out.write(hexlify(sha) + b'\n')
            reprogress()
    elif opt.tree or opt.commit or opt.name:
        if opt.name: # insert dummy_name which may be used as a restore target
            mode, sha = \
                split_to_blob_or_tree(new_blob, new_tree,
                                      hashsplit.from_config(files, split_cfg))
            splitfile_name = git.mangle_name(b'data', hashsplit.GIT_MODE_FILE, mode)
            shalist = [(mode, splitfile_name, sha)]
        else:
            shalist = split_to_shalist(new_blob, new_tree,
                                       hashsplit.from_config(files, split_cfg))
        tree = new_tree(shalist)
    else:
        last = 0
        for blob, level in hashsplit.from_config(files, split_cfg):
            hashsplit.total_split += len(blob)
            if opt.copy:
                out.write(blob)
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
        commit = new_commit(tree, parent, userline, opt.date,
                            None, userline, opt.date, None, msg)
        if opt.commit:
            out.write(hexlify(commit) + b'\n')

    return commit

def main(argv):
    reverse = environ.get(b'BUP_SERVER_REVERSE')
    opt_parser = options.Options(optspec)
    opt = opts_from_cmdline(opt_parser, argv, reverse)
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

    remote_dest = opt.remote or reverse
    writing = not (opt.noop or opt.copy)

    repo_checked = False
    def ensure_repo_checked():
        nonlocal repo_checked
        if not repo_checked:
            git.check_repo_or_die()
            repo_checked = True

    if opt.git_ids:
        # the input is actually a series of git object ids that we should retrieve
        # and split.
        #
        # This is a bit messy, but basically it converts from a series of
        # CatPipe.get() iterators into a series of file-type objects.
        # It would be less ugly if either CatPipe.get() returned a file-like object
        # (not very efficient), or split_to_shalist() expected an iterator instead
        # of a file.
        ensure_repo_checked()
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

    try:
        write_opts = {'compression_level': opt.compress,
                      'max_pack_size': opt.max_pack_size,
                      'max_pack_objects': opt.max_pack_objects}
        if opt.repo.startswith(b'file://'):
            # A repo isn't required for --noop or --copy, but if we do
            # have one, we need to respect its bup.split.files, etc.
            if writing:
                ensure_repo_checked()
                have_local_repo = True
            else:
                have_local_repo = git.establish_default_repo()
            repo = make_repo(opt.repo, **write_opts) if have_local_repo else None
        else:
            repo = make_repo(opt.repo, **write_opts)
    except client.ClientError as e:
        log('error: %s' % e)
        sys.exit(EXIT_FAILURE)

    # repo creation must be last nontrivial command in each if clause above
    with nullcontext_if_not(repo):
        try:
            if repo:
                split_cfg = hashsplit.configuration(repo.config_get)
            else:
                null_config_get = partial(git.git_config_get, os.devnull)
                split_cfg = hashsplit.configuration(null_config_get)
        except ConfigError as ex:
            opt_parser.fatal(ex)
        split_cfg['keep_boundaries'] = opt.keep_boundaries
        if opt.name and writing:
            refname = opt.name and b'refs/heads/%s' % opt.name
            oldref = repo.read_ref(refname)
        else:
            refname = oldref = None

        if writing:
            commit = split(opt, files, oldref, out, split_cfg,
                           new_blob=repo.write_data,
                           new_tree=repo.write_tree,
                           new_commit=repo.write_commit)
            if refname:
                repo.update_ref(refname, commit, oldref)
        else:
            assert not refname
            def null_write_data(content):
                return git.calc_hash(b'blob', content)
            def null_write_tree(shalist):
                return git.calc_hash(b'tree', git.tree_encode(shalist))
            split(opt, files, oldref, out, split_cfg,
                  new_blob=null_write_data, new_tree=null_write_tree)

    secs = time.time() - start_time
    size = hashsplit.total_split
    if opt.bench:
        log('bup: %.2f kbytes in %.2f secs = %.2f kbytes/sec\n'
            % (size / 1024, secs, size / 1024 / secs))
