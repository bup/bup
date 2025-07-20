
from __future__ import absolute_import, print_function
from collections import defaultdict
from itertools import chain, dropwhile, groupby, takewhile
from os import chdir
from random import choice, randint
from shutil import copytree, rmtree
from subprocess import PIPE
from sys import stderr
from time import localtime, strftime, time, tzset
import random, sys

if sys.version_info[:2] >= (3, 5):
    from difflib import diff_bytes, unified_diff
else:
    from difflib import unified_diff

from bup import compat
from bup.compat import environ
from bup.helpers import partition, period_as_secs, readpipe
from bup.io import byte_stream
from buptest import ex, exo
from wvpytest import wvfail, wvpass, wvpasseq, wvpassne, wvstart
import bup.path

if sys.version_info[:2] < (3, 5):
    def diff_bytes(_, *args):
        return unified_diff(*args)

def create_older_random_saves(n, start_utc, end_utc):
    with open(b'foo', 'wb') as f:
        pass
    ex([b'git', b'add', b'foo'])
    utcs = []
    while len(utcs) != n:
        utc = randint(start_utc, end_utc)
        utcs.append(utc)
    if n > 1: # ensure we have some duplicates
        for i in range(min(10, max(1, n // 3))):
            utcs[i] = utcs[-i]
    utcs = sorted(utcs)
    for i, utc in enumerate(utcs):
        with open(b'foo', 'wb') as f:
            f.write(b'%d\n' % i)
        ex([b'git', b'commit', b'--date', b'%d' % utc, b'-qam', b'%d' % utc])
    ex([b'git', b'gc', b'--aggressive'])
    return utcs

# There is corresponding code in bup for some of this, but the
# computation method is different here, in part so that the test can
# provide a more effective cross-check.

period_kinds = [b'all', b'dailies', b'monthlies', b'yearlies']
period_scale = {b's': 1,
                b'min': 60,
                b'h': 60 * 60,
                b'd': 60 * 60 * 24,
                b'w': 60 * 60 * 24 * 7,
                b'm': 60 * 60 * 24 * 31,
                b'y': 60 * 60 * 24 * 366}
period_scale_kinds = list(period_scale.keys())

def expected_retentions(utcs, utc_start, spec):
    if not spec:
        return utcs
    utcs = sorted(utcs, reverse=True)
    period_start = dict(spec)
    for kind, duration in period_start.items():
        period_start[kind] = utc_start - period_as_secs(duration)
    period_start = defaultdict(lambda: float('inf'), period_start)

    all = list(takewhile(lambda x: x >= period_start[b'all'], utcs))
    utcs = list(dropwhile(lambda x: x >= period_start[b'all'], utcs))

    matches = takewhile(lambda x: x >= period_start[b'dailies'], utcs)
    dailies = [max(day_utcs) for yday, day_utcs
               in groupby(matches, lambda x: localtime(x).tm_yday)]
    utcs = list(dropwhile(lambda x: x >= period_start[b'dailies'], utcs))

    matches = takewhile(lambda x: x >= period_start[b'monthlies'], utcs)
    monthlies = [max(month_utcs) for month, month_utcs
                 in groupby(matches, lambda x: localtime(x).tm_mon)]
    utcs = dropwhile(lambda x: x >= period_start[b'monthlies'], utcs)

    matches = takewhile(lambda x: x >= period_start[b'yearlies'], utcs)
    yearlies = [max(year_utcs) for year, year_utcs
                in groupby(matches, lambda x: localtime(x).tm_year)]

    return chain(all, dailies, monthlies, yearlies)

def period_spec(start_utc, end_utc):
    global period_kinds, period_scale, period_scale_kinds
    result = []
    desired_specs = randint(1, 2 * len(period_kinds))
    assert(desired_specs >= 1)  # At least one --keep argument is required
    while len(result) < desired_specs:
        period = None
        if randint(1, 100) <= 5:
            period = b'forever'
        else:
            assert(end_utc > start_utc)
            period_secs = randint(1, end_utc - start_utc)
            scale = choice(period_scale_kinds)
            mag = int(float(period_secs) / period_scale[scale])
            if mag != 0:
                period = (b'%d' % mag) + scale
        if period:
            result += [(choice(period_kinds), period)]
    return tuple(result)

def unique_period_specs(n, start_utc, end_utc):
    invocations = set()
    while len(invocations) < n:
        invocations.add(period_spec(start_utc, end_utc))
    return tuple(invocations)

def period_spec_to_period_args(spec):
    return tuple(chain(*((b'--keep-' + kind + b'-for', period)
                         for kind, period in spec)))

def result_diffline(x):
    return (b'%d %s\n'
            % (x, strftime(' %Y-%m-%d-%H%M%S', localtime(x)).encode('ascii')))

def check_prune_result(expected):
    actual = sorted([int(x)
                     for x in exo([b'git', b'log',
                                   b'--pretty=format:%at']).out.splitlines()])

    if expected != actual:
        for x in expected:
            print('ex:', x, strftime('%Y-%m-%d-%H%M%S', localtime(x)),
                  file=stderr)
        for line in diff_bytes(unified_diff,
                               [result_diffline(x) for x in expected],
                               [result_diffline(x) for x in actual],
                               fromfile=b'expected', tofile=b'actual'):
            sys.stderr.flush()
            byte_stream(sys.stderr).write(line)
    wvpass(expected == actual)


def test_prune_older(tmpdir):
    environ[b'GIT_AUTHOR_NAME'] = b'bup test'
    environ[b'GIT_COMMITTER_NAME'] = b'bup test'
    environ[b'GIT_AUTHOR_EMAIL'] = b'bup@a425bc70a02811e49bdf73ee56450e6f'
    environ[b'GIT_COMMITTER_EMAIL'] = b'bup@a425bc70a02811e49bdf73ee56450e6f'

    seed = int(environ.get(b'BUP_TEST_SEED', time()))
    random.seed(seed)
    print('random seed:', seed, file=stderr)

    save_population = int(environ.get(b'BUP_TEST_PRUNE_OLDER_SAVES', 2000))
    prune_cycles = int(environ.get(b'BUP_TEST_PRUNE_OLDER_CYCLES', 20))
    prune_gc_cycles = int(environ.get(b'BUP_TEST_PRUNE_OLDER_GC_CYCLES', 10))

    bup_cmd = bup.path.exe()

    environ[b'BUP_DIR'] = tmpdir + b'/work/.git'
    environ[b'GIT_DIR'] = tmpdir + b'/work/.git'
    now = int(time())
    three_years_ago = now - (60 * 60 * 24 * 366 * 3)
    chdir(tmpdir)
    ex([b'git', b'init', b'work'])
    ex([b'git', b'symbolic-ref', b'HEAD', b'refs/heads/main'])
    ex([b'git', b'config', b'gc.autoDetach', b'false'])

    wvstart('generating ' + str(save_population) + ' random saves')
    chdir(tmpdir + b'/work')
    save_utcs = create_older_random_saves(save_population, three_years_ago, now)
    chdir(tmpdir)
    test_set_hash = exo([b'git', b'show-ref', b'-s', b'main']).out.rstrip()
    ls_saves = exo((bup_cmd, b'ls', b'main')).out.splitlines()
    wvpasseq(save_population + 1, len(ls_saves))

    wvstart('ensure everything kept, if no keep arguments')
    ex([b'git', b'reset', b'--hard', test_set_hash])
    proc = ex((bup_cmd,
               b'prune-older', b'-v', b'--unsafe', b'--no-gc',
               b'--wrt', b'%d' % now) \
              + (b'main',),
              stdout=None, stderr=PIPE, check=False)
    wvpassne(proc.rc, 0)
    wvpass(b'at least one keep argument is required' in proc.err)
    check_prune_result(save_utcs)


    wvstart('running %d generative no-gc tests on %d saves' % (prune_cycles,
                                                               save_population))
    for spec in unique_period_specs(prune_cycles,
                                    # Make it more likely we'll have
                                    # some outside the save range.
                                    three_years_ago - period_scale[b'm'],
                                    now):
        ex([b'git', b'reset', b'--hard', test_set_hash])
        expected = sorted(expected_retentions(save_utcs, now, spec))
        ex((bup_cmd,
            b'prune-older', b'-v', b'--unsafe', b'--no-gc', b'--wrt',
            b'%d' % now) \
           + period_spec_to_period_args(spec) \
           + (b'main',))
        check_prune_result(expected)


    # More expensive because we have to recreate the repo each time
    wvstart('running %d generative gc tests on %d saves' % (prune_gc_cycles,
                                                            save_population))
    ex([b'git', b'reset', b'--hard', test_set_hash])
    copytree(b'work/.git', b'clean-test-repo', symlinks=True)
    for spec in unique_period_specs(prune_gc_cycles,
                                    # Make it more likely we'll have
                                    # some outside the save range.
                                    three_years_ago - period_scale[b'm'],
                                    now):
        rmtree(b'work/.git')
        copytree(b'clean-test-repo', b'work/.git')
        expected = sorted(expected_retentions(save_utcs, now, spec))
        ex((bup_cmd,
            b'prune-older', b'-v', b'--unsafe', b'--wrt', b'%d' % now) \
           + period_spec_to_period_args(spec) \
           + (b'main',))
        check_prune_result(expected)
