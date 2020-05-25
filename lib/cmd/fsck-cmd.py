#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import, print_function
import sys, os, glob, subprocess
from shutil import rmtree
from subprocess import PIPE, Popen
from tempfile import mkdtemp
from binascii import hexlify

from bup import options, git
from bup.compat import argv_bytes
from bup.helpers import Sha1, chunkyreader, istty2, log, progress
from bup.io import byte_stream


par2_ok = 0
nullf = open(os.devnull, 'wb+')

def debug(s):
    if opt.verbose > 1:
        log(s)

def run(argv):
    # at least in python 2.5, using "stdout=2" or "stdout=sys.stderr" below
    # doesn't actually work, because subprocess closes fd #2 right before
    # execing for some reason.  So we work around it by duplicating the fd
    # first.
    fd = os.dup(2)  # copy stderr
    try:
        p = subprocess.Popen(argv, stdout=fd, close_fds=False)
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

def par2(action, args, verb_floor=0):
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
    return run(cmd)

def par2_generate(base):
    return par2(b'create',
                [b'-n1', b'-c200', b'--', base, base + b'.pack', base + b'.idx'],
                verb_floor=2)

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
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])
opt.verbose = opt.verbose or 0

par2_setup()
if opt.par2_ok:
    if par2_ok:
        sys.exit(0)  # 'true' in sh
    else:
        sys.exit(1)
if opt.disable_par2:
    par2_ok = 0

git.check_repo_or_die()

if extra:
    extra = [argv_byes(x) for x in extra]
else:
    debug('fsck: No filenames given: checking all packs.\n')
    extra = glob.glob(git.repo(b'objects/pack/*.pack'))

sys.stdout.flush()
out = byte_stream(sys.stdout)
code = 0
count = 0
outstanding = {}
for name in extra:
    if name.endswith(b'.pack'):
        base = name[:-5]
    elif name.endswith(b'.idx'):
        base = name[:-4]
    elif name.endswith(b'.par2'):
        base = name[:-5]
    elif os.path.exists(name + b'.pack'):
        base = name
    else:
        raise Exception('%r is not a pack file!' % name)
    (dir,last) = os.path.split(base)
    par2_exists = os.path.exists(base + b'.par2')
    if par2_exists and os.stat(base + b'.par2').st_size == 0:
        par2_exists = 0
    sys.stdout.flush()  # Not sure we still need this, but it'll flush out too
    debug('fsck: checking %r (%s)\n'
          % (last, par2_ok and par2_exists and 'par2' or 'git'))
    if not opt.verbose:
        progress('fsck (%d/%d)\r' % (count, len(extra)))
    
    if not opt.jobs:
        nc = do_pack(base, last, par2_exists, out)
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
                sys.exit(do_pack(base, last, par2_exists, out))
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
sys.exit(code)
