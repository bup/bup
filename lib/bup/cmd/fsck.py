
from os import SEEK_END
from shutil import rmtree
from subprocess import DEVNULL, PIPE, run
from tempfile import mkdtemp
from os.path import join
import glob, os, sys

from bup import options, git
from bup.compat import argv_bytes
from bup.helpers \
    import (EXIT_FAILURE, EXIT_FALSE, EXIT_TRUE, EXIT_SUCCESS,
            Sha1, chunkyreader, istty2, log, progress, temp_dir)
from bup.io import byte_stream, path_msg


par2_ok = 0
opt = None

def debug(s):
    if opt.verbose > 1:
        log(s)

def par2_setup():
    global par2_ok
    try:
        run((b'par2', b'--help'), stdout=DEVNULL, stderr=DEVNULL, stdin=DEVNULL)
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
        p = run((b'par2', b'create', b'-qq', b'-t1', canary),
                stdout=PIPE, stderr=PIPE, stdin=DEVNULL)
        parallel = p.returncode == 0
        if opt.verbose:
            err = p.stderr
            if len(err) > 0 and err != b'Invalid option specified: -t1\n':
                log('Unexpected par2 error output\n')
                log(repr(err) + '\n')
            if parallel:
                log('Assuming par2 supports parallel processing\n')
            else:
                log('Assuming par2 does not support parallel processing\n')
        if p.stdout.strip(): # currently produces b'\n'
            log(f'Unexpected par2 create -qq output {p.stdout}\n')
        return parallel
    finally:
        rmtree(tmpdir)

_par2_parallel = None

def par2(action, args, verb_floor=0, cwd=None):
    global _par2_parallel
    if _par2_parallel is None:
        _par2_parallel = is_par2_parallel()
    cmd = [b'par2', action]
    if opt.verbose == verb_floor and not istty2:
        cmd.append(b'-q')
    elif opt.verbose > verb_floor and istty2:
        pass
    else:
        cmd.append(b'-qq')
    if _par2_parallel:
        cmd.append(b'-t1')
    cmd.extend(args)
    return run(cmd, stdout=2, cwd=cwd).returncode

def par2_generate(stem):
    parent, base = os.path.split(stem)
    # Work in a temp_dir because par2 was observed creating empty
    # files when interrupted by C-c.
    # cf. https://github.com/Parchive/par2cmdline/issues/84
    with temp_dir(dir=parent, prefix=(base + b'-bup-tmp-')) as tmpdir:
        pack = base + b'.pack'
        os.symlink(join(b'..', pack), join(tmpdir, pack))
        rc = par2(b'create', [b'-n1', b'-c200', b'--', base, pack],
                  verb_floor=2, cwd=tmpdir)
        if rc == 0:
            # Currently, there should only be two files, the par2
            # index and a single vol000+200 file, but let's be
            # defensive for the generation (keep whatever's produced).
            p2_idx = base + b'.par2'
            p2_vol = base + b'.vol000+200.par2'
            expected = frozenset((pack, p2_idx, p2_vol))
            for tmp in os.listdir(tmpdir):
                if tmp not in expected:
                    log(f'Unexpected par2 file (please report) {path_msg(tmp)}\n')
                if tmp in (p2_idx, pack):
                    continue
                os.rename(join(tmpdir, tmp), join(parent, tmp))
            # Let this indicate success
            os.rename(join(tmpdir, p2_idx), join(parent, p2_idx))
            expected = frozenset([pack])
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
    rc = par2(b'verify', [b'--', base], verb_floor=3)
    if rc != 0:
        log(f'error: par2 verify failed ({rc}) {path_msg(base)}\n')
        return False
    return True

def par2_repair(base):
    return par2(b'repair', [b'--', base], verb_floor=2)


def trailing_and_actual_checksum(path):
    try:
        f = open(path, 'rb')
    except FileNotFoundError:
        return None, None
    with f:
        f.seek(-20, SEEK_END)
        trailing = f.read(20)
        assert len(trailing) == 20
        f.seek(0)
        actual = Sha1()
        for b in chunkyreader(f, os.fstat(f.fileno()).st_size - 20):
            actual.update(b)
        return trailing, actual.digest()


def git_verify(stem, *, quick=False):
    if not quick:
        rc = run([b'git', b'verify-pack', b'--', stem]).returncode
        if rc == 0:
            return True
        log(f'error: git verify-pack failed ({rc}) {path_msg(stem)}\n')
        return False
    result = True
    for path in (stem + b'.idx', stem + b'.pack'):
        exp, act = trailing_and_actual_checksum(path)
        if act is None:
            log(f'error: missing {path_msg(path)}\n')
            result = False
        elif exp != act:
            log(f'error: expected {exp.hex()}, got {act.hex()}\n')
            result = False
    return result


def attempt_repair(stem, base, out, *, verbose=False):
    if git_verify(stem, quick=opt.quick):
        if opt.verbose: out.write(base + b' ok\n')
        return EXIT_SUCCESS
    rc = par2_repair(stem)
    if rc:
        log(f'{path_msg(base)} par2 repair: failed ({rc})\n')
        if verbose: out.write(base + b' failed\n')
        return EXIT_FAILURE
    log(f'{path_msg(base)} par2 repair: succeeded, checking .idx\n')
    try:
        exp, act = trailing_and_actual_checksum(stem + b'.idx')
        idx_ok = exp == act
        if not idx_ok:
            os.unlink(stem + b'.idx')
    except FileNotFoundError:
        idx_ok = False
    if not idx_ok:
        cmd = (b'git', b'index-pack', stem + b'.pack')
        idx_rc = run(cmd).returncode
        if idx_rc:
            log(f'{path_msg(base)} index-pack failed\n')
            if verbose: out.write(base + b' failed\n')
            return EXIT_FAILURE
        log(f'{path_msg(base)} index-pack succeeded\n')
    if verbose: out.write(base + b' repaired\n')
    # As with grep, test, and --par2-ok, we use 1 for communicating
    # information that's an expected possibility i.e. --repair needed
    # to repair.
    return EXIT_FALSE


def do_pack(mode, stem, par2_exists, out):
    assert mode in ('verify', 'generate', 'repair')
    # Note that par2 validation only tells us that the pack file
    # hasn't changed since the par2 generation.
    #
    # When making changes here, keep in mind that bup used to include
    # .idx files in the par2 recovery info, and we want to maintain
    # backward-compatibility.
    base = os.path.basename(stem)
    if mode == 'repair':
        return attempt_repair(stem, base, out, verbose=opt.verbose)
    if mode == 'verify':
        if not git_verify(stem, quick=opt.quick) \
           or (par2_ok and par2_exists and not par2_verify(stem)):
            if opt.verbose: out.write(base + b' failed\n')
            return EXIT_FAILURE
        if opt.verbose: out.write(base + b' ok\n')
        return EXIT_SUCCESS
    if mode == 'generate':
        if par2_exists:
            if opt.verbose: out.write(base + b' exists\n')
            return EXIT_TRUE
        rc = par2_generate(stem)
        if rc != EXIT_SUCCESS:
            log(f'{path_msg(base)} par2 create: failed ({rc})\n')
            if opt.verbose: out.write(base + b' failed\n')
            return EXIT_FAILURE
        if opt.verbose: out.write(base + b' generated\n')
        return EXIT_SUCCESS
    assert False, f'unexpected mode fsck {mode}'


optspec = """
bup fsck [options...] [packfile...]
--
r,repair    attempt to repair errors using par2 (dangerous!)
g,generate  generate auto-repair information using par2
v,verbose   increase verbosity (can be used more than once)
quick       just check pack sha1sum, don't use git verify-pack
j,jobs=     run 'n' jobs in parallel
par2-ok     immediately return 0 if par2 is ok, 1 if not
disable-par2  ignore par2 even if it is available
"""


def merge_exits(pending, new):
    """Return pending if it's an actual error, otherwise new if is.
    Barring that, prefer EXIT_FALSE over EXIT_SUCCESS."""
    if pending not in (EXIT_SUCCESS, EXIT_FALSE):
        return pending
    if new == EXIT_FALSE and pending == EXIT_SUCCESS:
        return EXIT_FALSE
    if new != EXIT_SUCCESS:
        return new
    return pending


def main(argv):
    global opt, par2_ok

    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    opt.verbose = opt.verbose or 0

    par2_setup()
    if opt.par2_ok:
        if extra or opt.repair or opt.generate or opt.quick or opt.jobs \
           or opt.disable_par2:
            o.fatal('--par2-ok is incompatible with the other options')
        sys.exit(EXIT_TRUE if par2_ok else EXIT_FALSE)
    if opt.disable_par2:
        par2_ok = 0
    if not par2_ok and (opt.generate or opt.repair):
        log(f'error: cannot --generate or --repair without par2\n')
        sys.exit(EXIT_FAILURE)

    if extra:
        pack_stems = [argv_bytes(x) for x in extra]
        for stem in pack_stems:
            if not stem.endswith(b'.pack'):
                o.fatal(f'packfile argument {path_msg(stem)} must end with .pack')
    else:
        debug('fsck: No filenames given: checking all packs.\n')
        git.check_repo_or_die()
        pack_stems = glob.glob(git.repo(b'objects/pack/*.pack'))

    pack_stems = [x[:-5] for x in pack_stems]

    sys.stdout.flush()
    out = byte_stream(sys.stdout)
    mode = 'repair' if opt.repair else 'generate' if opt.generate else 'verify'
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
            progress('fsck (%d/%d)\r' % (count, len(pack_stems)))

        if not opt.jobs:
            assert par2_status != False
            code = merge_exits(code, do_pack(mode, stem, par2_status, out))
            count += 1
        else:
            while len(outstanding) >= opt.jobs:
                (pid,nc) = os.wait()
                nc >>= 8
                if pid in outstanding:
                    del outstanding[pid]
                    code = merge_exits(code, nc)
                    count += 1
            pid = os.fork()
            if pid:  # parent
                outstanding[pid] = 1
            else: # child
                try:
                    assert par2_status != False
                    sys.exit(do_pack(mode, stem, par2_status, out))
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
            progress('fsck (%d/%d)\r' % (count, len(pack_stems)))
    if istty2:
        debug('fsck done.           \n')

    # double-check (e.g. for (unlikely) problems with generate tmpdir renames)
    for stem in pack_stems:
        if par2_recovery_file_status(stem) == False:
            if code == EXIT_SUCCESS:
                code = EXIT_FAILURE

    sys.exit(code)
