
import os, glob

from bup import options, git, bloom
from bup.compat import argv_bytes
from bup.helpers \
    import (add_error,
            debug1,
            log,
            note_error,
            progress,
            qprogress,
            saved_errors)
from bup.io import path_msg


optspec = """
bup bloom [options...]
--
ruin       ruin the specified bloom file (clearing the bitfield)
f,force    ignore existing bloom file and regenerate it from scratch
o,output=  output bloom filename (default: auto)
d,dir=     input directory to look for idx files (default: auto)
k,hashes=  number of hash functions to use (4 or 5) (default: auto)
c,check=   check given *.idx or *.midx file against the bloom filter
"""


def ruin_bloom(bloomfilename):
    if not os.path.exists(bloomfilename):
        log(path_msg(bloomfilename) + '\n')
        add_error('bloom: %s not found to ruin\n' % path_msg(bloomfilename))
        return
    with bloom.ShaBloom(bloomfilename, readwrite=True, expected=1) as b:
        b.map[16 : 16 + 2**b.bits] = b'\0' * 2**b.bits


def check_bloom(path, bloomfilename, idx):
    rbloomfilename = git.repo_rel(bloomfilename)
    ridx = git.repo_rel(idx)
    if not os.path.exists(bloomfilename):
        log('bloom: %s: does not exist.\n' % path_msg(rbloomfilename))
        return
    with bloom.ShaBloom(bloomfilename) as b:
        if not b.valid():
            add_error('bloom: %r is invalid.\n' % path_msg(rbloomfilename))
            return
        base = os.path.basename(idx)
        if base not in b.idxnames:
            log('bloom: %s does not contain the idx.\n' % path_msg(rbloomfilename))
            return
        if base == idx:
            idx = os.path.join(path, idx)
        log('bloom: bloom file: %s\n' % path_msg(rbloomfilename))
        log('bloom:   checking %s\n' % path_msg(ridx))
        oids = git.open_object_idx(idx)
        if not oids:
            note_error(f'bloom: ERROR: invalid index {path_msg(idx)}\n')
            return
        with oids:
            for oid in oids:
                if not b.exists(oid):
                    add_error('bloom: ERROR: object %s missing' % oid.hex())


_first = None
def do_bloom(path, outfilename, k, force):
    global _first
    assert k in (None, 4, 5)
    b = None
    try:
        if os.path.exists(outfilename) and not force:
            b = bloom.ShaBloom(outfilename)
            if not b.valid():
                debug1("bloom: Existing invalid bloom found, regenerating.\n")
                b.close()
                b = None

        add = []
        rest = []
        add_count = 0
        rest_count = 0
        for i, name in enumerate(glob.glob(b'%s/*.idx' % path)):
            progress('bloom: counting: %d\r' % i)
            with git.open_idx(name) as ix:
                ixbase = os.path.basename(name)
                if b is not None and (ixbase in b.idxnames):
                    rest.append(name)
                    rest_count += len(ix)
                else:
                    add.append(name)
                    add_count += len(ix)

        if not add:
            debug1("bloom: nothing to do.\n")
            return

        if b is not None:
            if len(b) != rest_count:
                debug1("bloom: size %d != idx total %d, regenerating\n"
                       % (len(b), rest_count))
                b, b_tmp = None, b
                b_tmp.close()
            elif k is not None and k != b.k:
                debug1("bloom: new k %d != existing k %d, regenerating\n"
                       % (k, b.k))
                b, b_tmp = None, b
                b_tmp.close()
            elif (b.bits < bloom.MAX_BLOOM_BITS[b.k] and
                  b.pfalse_positive(add_count) > bloom.MAX_PFALSE_POSITIVE):
                debug1("bloom: regenerating: adding %d entries gives "
                       "%.2f%% false positives.\n"
                       % (add_count, b.pfalse_positive(add_count)))
                b, b_tmp = None, b
                b_tmp.close()
            else:
                b, b_tmp = None, b
                b_tmp.close()
                b = bloom.ShaBloom(outfilename, readwrite=True,
                                   expected=add_count)
        if b is None: # Need all idxs to build from scratch
            add += rest
            add_count += rest_count
        del rest
        del rest_count

        msg = b is None and 'creating from' or 'adding'
        if not _first: _first = path
        dirprefix = (_first != path) and git.repo_rel(path) + b': ' or b''
        progress('bloom: %s%s %d file%s (%d object%s).\r'
            % (path_msg(dirprefix), msg,
               len(add), len(add)!=1 and 's' or '',
               add_count, add_count!=1 and 's' or ''))

        tfname = None
        if b is None:
            tfname = os.path.join(path, b'bup.tmp.bloom')
            b = bloom.create(tfname, expected=add_count, k=k)
        count = 0
        icount = 0
        for name in add:
            with git.open_idx(name) as ix:
                qprogress('bloom: writing %.2f%% (%d/%d objects)\r'
                          % (icount*100.0/add_count, icount, add_count))
                b.add_idx(ix)
                count += 1
                icount += len(ix)

    finally:  # This won't handle pending exceptions correctly in py2
        # Currently, there's an open file object for tfname inside b.
        # Make sure it's closed before rename.
        if b is not None: b.close()

    if tfname:
        os.rename(tfname, outfilename)


def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])

    if extra:
        o.fatal('no positional parameters expected')

    if not opt.check and opt.k and opt.k not in (4,5):
        o.fatal('only k values of 4 and 5 are supported')

    if opt.check:
        opt.check = argv_bytes(opt.check)

    output = argv_bytes(opt.output) if opt.output else None
    if opt.dir:
        path = argv_bytes(opt.dir)
    else:
        git.check_repo_or_die()
        path = git.repo(b'objects/pack')
    debug1('bloom: scanning %s\n' % path_msg(path))
    outfilename = output or os.path.join(path, b'bup.bloom')
    if opt.check:
        check_bloom(path, outfilename, opt.check)
    elif opt.ruin:
        ruin_bloom(outfilename)
    else:
        do_bloom(path, outfilename, opt.k, opt.force)

    if not saved_errors:
        log('All tests passed.\n')
