
from shutil import rmtree
from subprocess import PIPE
from tempfile import mkdtemp
from binascii import hexlify
from os.path import join
import glob, os, subprocess, sys

from bup import options, git
from bup.compat import argv_bytes
from bup.helpers \
    import (EXIT_FAILURE, EXIT_FALSE, EXIT_TRUE, EXIT_SUCCESS,
            Sha1, chunkyreader, istty2, log, progress, temp_dir)
from bup.io import byte_stream, path_msg


par2_ok = 0
nullf = open(os.devnull, 'wb+')
opt = None

def debug(s):
    if opt.verbose > 1:
        log(s)

def run(argv, *, cwd=None):
    # at least in python 2.5, using "stdout=2" or "stdout=sys.stderr" below
    # doesn't actually work, because subprocess closes fd #2 right before
    # execing for some reason.  So we work around it by duplicating the fd
    # first.
    fd = os.dup(2)  # copy stderr
    try:
        p = subprocess.Popen(argv, stdout=fd, close_fds=False, cwd=cwd)
        return p.wait()
    finally:
        os.close(fd)

def par2_setup():
    global par2_ok
    rv = 1
    try:
        p = subprocess.Popen([b'par2', b'--help'],
                             stdout=nullf, stderr=nullf, stdin=nullf)
        rv = p.wait()
    except OSError:
        log('fsck: warning: par2 not found; disabling recovery features.\n')
    else:
        par2_ok = 1

def is_par2_parallel():
    # A true result means it definitely allows -t1; a false result is
    # technically inconclusive, but likely means no.
    tmpdir = mkdtemp(prefix=b'bup-fsck')
    try:
        canary = tmpdir + b'/canary'
        with open(canary, 'wb') as f:
            f.write(b'canary\n')
        p = subprocess.Popen((b'par2', b'create', b'-qq', b'-t1', canary),
                             stderr=PIPE, stdin=nullf)
        _, err = p.communicate()
        parallel = p.returncode == 0
        if opt.verbose:
            if len(err) > 0 and err != b'Invalid option specified: -t1\n':
                log('Unexpected par2 error output\n')
                log(repr(err) + '\n')
            if parallel:
                log('Assuming par2 supports parallel processing\n')
            else:
                log('Assuming par2 does not support parallel processing\n')
        return parallel
    finally:
        rmtree(tmpdir)

_par2_parallel = None

def par2(action, args, verb_floor=0, cwd=None):
    global _par2_parallel
    if _par2_parallel is None:
        _par2_parallel = is_par2_parallel()
    cmd = [b'par2', action]
    if opt.verbose >= verb_floor and not istty2:
        cmd.append(b'-q')
    else:
        cmd.append(b'-qq')
    if _par2_parallel:
        cmd.append(b'-t1')
    cmd.extend(args)
    return run(cmd, cwd=cwd)

def par2_generate(stem):
    parent, base = os.path.split(stem)
    # Work in a temp_dir because par2 was observed creating empty
    # files when interrupted by C-c.
    # cf. https://github.com/Parchive/par2cmdline/issues/84
    with temp_dir(dir=parent, prefix=(base + b'-bup-tmp-')) as tmpdir:
        idx = base + b'.idx'
        pack = base + b'.pack'
        os.symlink(join(b'..', idx), join(tmpdir, idx))
        os.symlink(join(b'..', pack), join(tmpdir, pack))
        rc = par2(b'create', [b'-n1', b'-c200', b'--', base, pack, idx],
                  verb_floor=2, cwd=tmpdir)
        if rc == 0:
            # Currently, there should only be two files, the par2
            # index and a single vol000+200 file, but let's be
            # defensive for the generation (keep whatever's produced).
            p2_idx = base + b'.par2'
            p2_vol = base + b'.vol000+200.par2'
            expected = frozenset((idx, pack, p2_idx, p2_vol))
            for tmp in os.listdir(tmpdir):
                if tmp not in expected:
                    log(f'Unexpected par2 file (please report) {path_msg(tmp)}\n')
                if tmp in (p2_idx, idx, pack):
                    continue
                os.rename(join(tmpdir, tmp), join(parent, tmp))
            # Let this indicate success
            os.rename(join(tmpdir, p2_idx), join(parent, p2_idx))
            expected = frozenset((idx, pack))
            remaining = frozenset(os.listdir(tmpdir))
            assert expected == remaining
        return rc

def par2_recovery_file_status(stem):
    """Return True if recovery files exist for the stem and we should
    assume they're acceptable.  Return None if none of them exist, and
    return False (after logging appropriate errors) if something
    appears to be wrong with them, for example, if any of the files
    are empty, or if the set of files is incomplete.

    """
    # Look for empty *.par2 files because C-c during "par2 create" may
    # leave them when interrupted, and previous versions of bup didn't
    # run par2 create in a tempdir to compensate.  For now, we decide
    # the existing data is OK if the pack-HASH.par2 and
    # pack-HASH.vol000+200.par2 files exist, and neither is empty.
    # cf. https://github.com/Parchive/par2cmdline/issues/84
    paths = [stem + suffix for suffix in (b'.par2', b'.vol000+200.par2')]
    empty = []
    missing = set(paths)
    for path in paths:
        try:
            st = os.stat(path)
            if st.st_size == 0:
                empty.append(path)
            else:
                missing.remove(path)
        except FileNotFoundError:
            pass
    for path in empty:
        log(f'error: empty par2 file - {path_msg(path)}\n')
    if empty:
        return False
    if len(missing) == 2:
        return None
    for path in missing:
        log(f'error: missing par2 file - {path_msg(path)}\n')
    if not missing:
        return True
    return False

def par2_verify(base):
    return par2(b'verify', [b'--', base], verb_floor=3)

def par2_repair(base):
    return par2(b'repair', [b'--', base], verb_floor=2)

def quick_verify(base):
    f = open(base + b'.pack', 'rb')
    f.seek(-20, 2)
    wantsum = f.read(20)
    assert(len(wantsum) == 20)
    f.seek(0)
    sum = Sha1()
    for b in chunkyreader(f, os.fstat(f.fileno()).st_size - 20):
        sum.update(b)
    if sum.digest() != wantsum:
        raise ValueError('expected %r, got %r' % (hexlify(wantsum),
                                                  sum.hexdigest()))


def git_verify(base):
    if opt.quick:
        try:
            quick_verify(base)
        except Exception as e:
            log('error: %s\n' % e)
            return 1
        return 0
    else:
        return run([b'git', b'verify-pack', b'--', base])


def do_pack(base, last, par2_exists, out):
    code = 0
    if par2_ok and par2_exists and (opt.repair or not opt.generate):
        vresult = par2_verify(base)
        if vresult != 0:
            if opt.repair:
                rresult = par2_repair(base)
                if rresult != 0:
                    action_result = b'failed'
                    log('%s par2 repair: failed (%d)\n' % (last, rresult))
                    code = rresult
                else:
                    action_result = b'repaired'
                    log('%s par2 repair: succeeded (0)\n' % last)
                    # FIXME: for this to be useful, we need to define
                    # the semantics, e.g. what's promised when we have
                    # this and a competing error from another pack?
                    code = 100
            else:
                action_result = b'failed'
                log('%s par2 verify: failed (%d)\n' % (last, vresult))
                code = vresult
        else:
            action_result = b'ok'
    elif not opt.generate or (par2_ok and not par2_exists):
        gresult = git_verify(base)
        if gresult != 0:
            action_result = b'failed'
            log('%s git verify: failed (%d)\n' % (last, gresult))
            code = gresult
        else:
            if par2_ok and opt.generate:
                presult = par2_generate(base)
                if presult != 0:
                    action_result = b'failed'
                    log('%s par2 create: failed (%d)\n' % (last, presult))
                    code = presult
                else:
                    action_result = b'generated'
            else:
                action_result = b'ok'
    else:
        assert(opt.generate and (not par2_ok or par2_exists))
        action_result = b'exists' if par2_exists else b'skipped'
    if opt.verbose:
        out.write(last + b' ' +  action_result + b'\n')
    return code


optspec = """
bup fsck [options...] [filenames...]
--
r,repair    attempt to repair errors using par2 (dangerous!)
g,generate  generate auto-repair information using par2
v,verbose   increase verbosity (can be used more than once)
quick       just check pack sha1sum, don't use git verify-pack
j,jobs=     run 'n' jobs in parallel
par2-ok     immediately return 0 if par2 is ok, 1 if not
disable-par2  ignore par2 even if it is available
"""

def main(argv):
    global opt, par2_ok

    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    opt.verbose = opt.verbose or 0

    par2_setup()
    if opt.par2_ok:
        sys.exit(EXIT_TRUE if par2_ok else EXIT_FALSE)
    if opt.disable_par2:
        par2_ok = 0

    if extra:
        extra = [argv_bytes(x) for x in extra]
    else:
        debug('fsck: No filenames given: checking all packs.\n')
        git.check_repo_or_die()
        extra = glob.glob(git.repo(b'objects/pack/*.pack'))

    pack_stems = []
    for name in extra:
        if name.endswith(b'.pack'):
            pack_stems.append(name[:-5])
        elif name.endswith(b'.idx'):
            pack_stems.append(name[:-4])
        elif name.endswith(b'.par2'):
            pack_stems.append(name[:-5])
        elif os.path.exists(name + b'.pack'):
            pack_stems.append(name)
        else:
            raise Exception('%r is not a pack file!' % name)

    sys.stdout.flush()
    out = byte_stream(sys.stdout)
    code = EXIT_SUCCESS
    count = 0
    outstanding = {}
    for stem in pack_stems:
        base = os.path.basename(stem)
        par2_status = par2_recovery_file_status(stem)
        if par2_status == False:
            if code == EXIT_SUCCESS:
                code = EXIT_FAILURE
            continue
        sys.stdout.flush()  # Not sure we still need this, but it'll flush out too
        debug('fsck: checking %r (%s)\n'
              % (base, par2_ok and par2_status and 'par2' or 'git'))
        if not opt.verbose:
            progress('fsck (%d/%d)\r' % (count, len(extra)))

        if not opt.jobs:
            assert par2_status != False
            nc = do_pack(stem, base, par2_status, out)
            # FIXME: is first wins what we really want (cf. repair's 100)
            code = code or nc
            count += 1
        else:
            while len(outstanding) >= opt.jobs:
                (pid,nc) = os.wait()
                nc >>= 8
                if pid in outstanding:
                    del outstanding[pid]
                    code = code or nc
                    count += 1
            pid = os.fork()
            if pid:  # parent
                outstanding[pid] = 1
            else: # child
                try:
                    assert par2_status != False
                    sys.exit(do_pack(stem, base, par2_status, out))
                except Exception as e:
                    log('exception: %r\n' % e)
                    sys.exit(99)

    while len(outstanding):
        (pid,nc) = os.wait()
        nc >>= 8
        if pid in outstanding:
            del outstanding[pid]
            code = code or nc
            count += 1
        if not opt.verbose:
            progress('fsck (%d/%d)\r' % (count, len(extra)))
    if istty2:
        debug('fsck done.           \n')

    # double-check (e.g. for (unlikely) problems with generate tmpdir renames)
    for stem in pack_stems:
        if par2_recovery_file_status(stem) == False:
            if code == EXIT_SUCCESS:
                code = EXIT_FAILURE

    sys.exit(code)
