
from __future__ import absolute_import, print_function
from binascii import hexlify
import glob, os, math, resource, struct, sys

from bup import options, git, midx, _helpers, xstat
from bup.compat import ExitStack, argv_bytes, hexstr
from bup.helpers import (Sha1, add_error, atomically_replaced_file, debug1,
                         fdatasync, fsync,
                         log, mmap_readwrite, qprogress,
                         saved_errors, unlink)
from bup.io import byte_stream, path_msg
from bup.midx import MissingIdxs, open_midx


PAGE_SIZE=4096
SHA_PER_PAGE=PAGE_SIZE/20.

optspec = """
bup midx [options...] <idxnames...>
--
o,output=  output midx filename (default: auto-generated)
a,auto     automatically use all existing .midx/.idx files as input
f,force    merge produce exactly one .midx containing all objects
p,print    print names of generated midx files
check      validate contents of the given midx files (with -a, all midx files)
max-files= maximum number of idx files to open at once [-1]
d,dir=     directory containing idx/midx files
"""

merge_into = _helpers.merge_into


def _group(l, count):
    for i in range(0, len(l), count):
        yield l[i:i+count]


def max_files():
    mf = min(resource.getrlimit(resource.RLIMIT_NOFILE))
    if mf > 32:
        mf -= 20  # just a safety margin
    else:
        mf -= 6   # minimum safety margin
    return mf


def _maybe_open_midx(path, *, rm_broken=False):
    """Return a PackMidx for path as open_midx() does unless some of
    its idx files are missing.  In that case, warn, delete the path
    if rm_broken is true, and return None.
    """
    missing = None
    try:
        return open_midx(path, ignore_missing=False)
    except MissingIdxs as ex:
        missing = ex.paths
    pathm = path_msg(path)
    # FIXME: eventually note_error instead when we're not deleting?
    for idx in missing:
        idxm = path_msg(idx)
        log(f'warning: midx {pathm} refers to mssing idx {idxm}\n')
    if rm_broken:
        log(f'Removing incomplete midx {pathm}\n')
        unlink(path)
    return None


def check_midx(name):
    nicename = git.repo_rel(name)
    log('Checking %s.\n' % path_msg(nicename))
    try:
        ix = git.open_object_idx(name)
    except git.GitError as e:
        add_error('%s: %s' % (path_msg(name), e))
    if not ix:
        return
    with ix:
        for count,subname in enumerate(ix.idxnames):
            sub = git.open_object_idx(os.path.join(os.path.dirname(name), subname))
            if not sub:
                continue
            with sub:
                for ecount,e in enumerate(sub):
                    if not (ecount % 1234):
                        qprogress('  %d/%d: %s %d/%d\r'
                                  % (count, len(ix.idxnames),
                                     git.shorten_hash(subname).decode('ascii'),
                                     ecount, len(sub)))
                    if not sub.exists(e):
                        add_error("%s: %s: %s missing from idx"
                                  % (path_msg(nicename),
                                     git.shorten_hash(subname).decode('ascii'),
                                     hexstr(e)))
                    if not ix.exists(e):
                        add_error("%s: %s: %s missing from midx"
                                  % (path_msg(nicename),
                                     git.shorten_hash(subname).decode('ascii'),
                                     hexstr(e)))
        prev = None
        for ecount,e in enumerate(ix):
            if not (ecount % 1234):
                qprogress('  Ordering: %d/%d\r' % (ecount, len(ix)))
            if e and prev and not e >= prev:
                add_error('%s: ordering error: %s < %s'
                          % (nicename, hexstr(e), hexstr(prev)))
            prev = e


_first = None
def _do_midx(outdir, outfilename, infilenames, prefixstr,
             auto=False, force=False):
    global _first
    if not outfilename:
        assert(outdir)
        sum = hexlify(Sha1(b'\0'.join(infilenames)).digest())
        outfilename = b'%s/midx-%s.midx' % (outdir, sum)

    inp = []
    total = 0
    allfilenames = []
    with ExitStack() as contexts:
        for name in infilenames:
            if name.endswith(b'.idx'):
                ix = git.open_idx(name)
            else:
                ix = _maybe_open_midx(name, rm_broken=auto or force)
            if not ix:
                continue
            contexts.enter_context(ix)
            inp.append((
                ix.map,
                len(ix),
                ix.sha_ofs,
                isinstance(ix, midx.PackMidx) and ix.which_ofs or 0,
                len(allfilenames),
            ))
            for n in ix.idxnames:
                # FIXME: double-check wrt outfilename above
                allfilenames.append(os.path.basename(n))
            total += len(ix)
        inp.sort(reverse=True, key=lambda x: x[0][x[2] : x[2] + 20])

        if not _first: _first = outdir
        dirprefix = (_first != outdir) and git.repo_rel(outdir) + b': ' or b''
        debug1('midx: %s%screating from %d files (%d objects).\n'
               % (dirprefix, prefixstr, len(infilenames), total))
        if (auto and (total < 1024 and len(infilenames) < 3)) \
           or ((auto or force) and len(infilenames) < 2) \
           or (force and not total):
            debug1('midx: nothing to do.\n')
            return None

        pages = int(total/SHA_PER_PAGE) or 1
        bits = int(math.ceil(math.log(pages, 2)))
        entries = 2**bits
        debug1('midx: table size: %d (%d bits)\n' % (entries*4, bits))

        unlink(outfilename)
        with atomically_replaced_file(outfilename, 'w+b') as f:
            f.write(b'MIDX')
            f.write(struct.pack('!II', midx.MIDX_VERSION, bits))
            assert(f.tell() == 12)

            f.truncate(12 + 4*entries + 20*total + 4*total)
            f.flush()
            fdatasync(f.fileno())

            with mmap_readwrite(f, close=False) as fmap:
                count = merge_into(fmap, bits, total, inp)
            f.seek(0, os.SEEK_END)
            f.write(b'\0'.join(allfilenames))
            f.flush()
            fsync(f.fileno())

    # This is just for testing (if you enable this, don't clear inp above)
    # if 0:
    #     p = midx.open_midx(outfilename)
    #     assert(len(p.idxnames) == len(infilenames))
    #     log(repr(p.idxnames) + '\n')
    #     assert(len(p) == total)
    #     for pe, e in p, git.idxmerge(inp, final_progress=False):
    #         pin = next(pi)
    #         assert(i == pin)
    #         assert(p.exists(i))

    return total, outfilename


def do_midx(outdir, outfilename, infilenames, prefixstr, prout,
            auto=False, force=False, print_names=False):
    rv = _do_midx(outdir, outfilename, infilenames, prefixstr,
                  auto=auto, force=force)
    if rv and print_names:
        prout.write(rv[1] + b'\n')


def do_midx_dir(path, outfilename, prout, auto=False, force=False,
                max_files=-1, print_names=False):
    already = {}
    sizes = {}
    if force and not auto:
        midxs = []   # don't use existing midx files
    else:
        midxs = []
        contents = {}
        for mname in glob.glob(b'%s/*.midx' % path):
            m = _maybe_open_midx(mname, rm_broken=auto or force)
            if not m:
                continue
            with m:
                midxs.append(mname)
                contents[mname] = [(b'%s/%s' % (path,i)) for i in m.idxnames]
                sizes[mname] = len(m)

        # sort the biggest+newest midxes first, so that we can eliminate
        # smaller (or older) redundant ones that come later in the list
        midxs.sort(key=lambda ix: (-sizes[ix], -xstat.stat(ix).st_mtime))

        for mname in midxs:
            any = 0
            for iname in contents[mname]:
                if not already.get(iname):
                    already[iname] = 1
                    any = 1
            if not any:
                debug1('%r is redundant\n' % mname)
                unlink(mname)
                already[mname] = 1

    midxs = [k for k in midxs if not already.get(k)]
    idxs = [k for k in glob.glob(b'%s/*.idx' % path) if not already.get(k)]

    for iname in idxs:
        with git.open_idx(iname) as i:
            sizes[iname] = len(i)

    all = [(sizes[n],n) for n in (midxs + idxs)]

    # FIXME: what are the optimal values?  Does this make sense?
    DESIRED_HWM = force and 1 or 5
    DESIRED_LWM = force and 1 or 2
    existed = dict((name,1) for sz,name in all)
    debug1('midx: %d indexes; want no more than %d.\n'
           % (len(all), DESIRED_HWM))
    if len(all) <= DESIRED_HWM:
        debug1('midx: nothing to do.\n')
    while len(all) > DESIRED_HWM:
        all.sort()
        part1 = [name for sz,name in all[:len(all)-DESIRED_LWM+1]]
        part2 = all[len(all)-DESIRED_LWM+1:]
        all = list(do_midx_group(path, outfilename, part1,
                                 auto=auto, force=force, max_files=max_files)) \
                                 + part2
        if len(all) > DESIRED_HWM:
            debug1('\nStill too many indexes (%d > %d).  Merging again.\n'
                   % (len(all), DESIRED_HWM))

    if print_names:
        for sz,name in all:
            if not existed.get(name):
                prout.write(name + b'\n')


def do_midx_group(outdir, outfilename, infiles, auto=False, force=False,
                  max_files=-1):
    groups = list(_group(infiles, max_files))
    gprefix = ''
    for n,sublist in enumerate(groups):
        if len(groups) != 1:
            gprefix = 'Group %d: ' % (n+1)
        rv = _do_midx(outdir, outfilename, sublist, gprefix,
                      auto=auto, force=force)
        if rv:
            yield rv


def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    opt.output = argv_bytes(opt.output) if opt.output else None

    if extra and (opt.auto or opt.force):
        o.fatal("you can't use -f/-a and also provide filenames")
    if opt.check and (not extra and not opt.auto):
        o.fatal("if using --check, you must provide filenames or -a")

    git.check_repo_or_die()

    if opt.max_files < 0:
        opt.max_files = max_files()
    assert(opt.max_files >= 5)

    path = opt.dir and argv_bytes(opt.dir) or git.repo(b'objects/pack')

    extra = [argv_bytes(x) for x in extra]

    if opt.check:
        # check existing midx files
        if extra:
            midxes = extra
        else:
            debug1('midx: scanning %s\n' % path)
            midxes = glob.glob(os.path.join(path, b'*.midx'))
        for name in midxes:
            check_midx(name)
        if not saved_errors:
            log('All tests passed.\n')
    else:
        if extra:
            sys.stdout.flush()
            do_midx(path, opt.output, extra, b'',
                    byte_stream(sys.stdout), auto=opt.auto, force=opt.force,
                    print_names=opt.print)
        elif opt.auto or opt.force:
            sys.stdout.flush()
            debug1('midx: scanning %s\n' % path_msg(path))
            do_midx_dir(path, opt.output, byte_stream(sys.stdout),
                        auto=opt.auto, force=opt.force,
                        max_files=opt.max_files)
        else:
            o.fatal("you must use -f or -a or provide input filenames")

    if saved_errors:
        log('WARNING: %d errors encountered.\n' % len(saved_errors))
        sys.exit(1)
