#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import, print_function
from binascii import hexlify, unhexlify
from collections import defaultdict
from itertools import groupby
from sys import stderr
from time import localtime, strftime, time
import re, sys

from bup import git, options
from bup.compat import argv_bytes, int_types
from bup.gc import bup_gc
from bup.helpers import die_if_errors, log, partition, period_as_secs
from bup.io import byte_stream
from bup.repo import LocalRepo
from bup.rm import bup_rm


def branches(refnames=tuple()):
    return ((name[11:], hexlify(sha)) for (name,sha)
            in git.list_refs(patterns=(b'refs/heads/' + n for n in refnames),
                             limit_to_heads=True))

def save_name(branch, utc):
    return branch + b'/' \
            + strftime('%Y-%m-%d-%H%M%S', localtime(utc)).encode('ascii')

def classify_saves(saves, period_start):
    """For each (utc, id) in saves, yield (True, (utc, id)) if the save
    should be kept and (False, (utc, id)) if the save should be removed.
    The ids are binary hashes.
    """

    def retain_newest_in_region(region):
        for save in region[0:1]:
            yield True, save
        for save in region[1:]:
            yield False, save

    matches, rest = partition(lambda s: s[0] >= period_start['all'], saves)
    for save in matches:
        yield True, save

    tm_ranges = ((period_start['dailies'], lambda s: localtime(s[0]).tm_yday),
                 (period_start['monthlies'], lambda s: localtime(s[0]).tm_mon),
                 (period_start['yearlies'], lambda s: localtime(s[0]).tm_year))

    # Break the decreasing utc sorted saves up into the respective
    # period ranges (dailies, monthlies, ...).  Within each range,
    # group the saves by the period scale (days, months, ...), and
    # then yield a "keep" action (True, utc) for the newest save in
    # each group, and a "drop" action (False, utc) for the rest.
    for pstart, time_region_id in tm_ranges:
        matches, rest = partition(lambda s: s[0] >= pstart, rest)
        for region_id, region_saves in groupby(matches, time_region_id):
            for action in retain_newest_in_region(list(region_saves)):
                yield action

    # Finally, drop any saves older than the specified periods
    for save in rest:
        yield False, save


optspec = """
bup prune-older [options...] [BRANCH...]
--
keep-all-for=       retain all saves within the PERIOD
keep-dailies-for=   retain the newest save per day within the PERIOD
keep-monthlies-for= retain the newest save per month within the PERIOD
keep-yearlies-for=  retain the newest save per year within the PERIOD
wrt=                end all periods at this number of seconds since the epoch
pretend       don't prune, just report intended actions to standard output
gc            collect garbage after removals [1]
gc-threshold= only rewrite a packfile if it's over this percent garbage [10]
#,compress=   set compression level to # (0-9, 9 is highest) [1]
v,verbose     increase log output (can be used more than once)
unsafe        use the command even though it may be DANGEROUS
"""

o = options.Options(optspec)
opt, flags, roots = o.parse(sys.argv[1:])
roots = [argv_bytes(x) for x in roots]

if not opt.unsafe:
    o.fatal('refusing to run dangerous, experimental command without --unsafe')

now = int(time()) if opt.wrt is None else opt.wrt
if not isinstance(now, int_types):
    o.fatal('--wrt value ' + str(now) + ' is not an integer')

period_start = {}
for period, extent in (('all', opt.keep_all_for),
                       ('dailies', opt.keep_dailies_for),
                       ('monthlies', opt.keep_monthlies_for),
                       ('yearlies', opt.keep_yearlies_for)):
    if extent:
        secs = period_as_secs(extent.encode('ascii'))
        if not secs:
            o.fatal('%r is not a valid period' % extent)
        period_start[period] = now - secs

if not period_start:
    o.fatal('at least one keep argument is required')

period_start = defaultdict(lambda: float('inf'), period_start)

if opt.verbose:
    epoch_ymd = strftime('%Y-%m-%d-%H%M%S', localtime(0))
    for kind in ['all', 'dailies', 'monthlies', 'yearlies']:
        period_utc = period_start[kind]
        if period_utc != float('inf'):
            if not (period_utc > float('-inf')):
                log('keeping all ' + kind)
            else:
                try:
                    when = strftime('%Y-%m-%d-%H%M%S', localtime(period_utc))
                    log('keeping ' + kind + ' since ' + when + '\n')
                except ValueError as ex:
                    if period_utc < 0:
                        log('keeping %s since %d seconds before %s\n'
                            %(kind, abs(period_utc), epoch_ymd))
                    elif period_utc > 0:
                        log('keeping %s since %d seconds after %s\n'
                            %(kind, period_utc, epoch_ymd))
                    else:
                        log('keeping %s since %s\n' % (kind, epoch_ymd))

git.check_repo_or_die()

# This could be more efficient, but for now just build the whole list
# in memory and let bup_rm() do some redundant work.

def parse_info(f):
    author_secs = f.readline().strip()
    return int(author_secs)

sys.stdout.flush()
out = byte_stream(sys.stdout)

removals = []
for branch, branch_id in branches(roots):
    die_if_errors()
    saves = ((utc, unhexlify(oidx)) for (oidx, utc) in
             git.rev_list(branch_id, format=b'%at', parse=parse_info))
    for keep_save, (utc, id) in classify_saves(saves, period_start):
        assert(keep_save in (False, True))
        # FIXME: base removals on hashes
        if opt.pretend:
            out.write(b'+ ' if keep_save else b'- '
                      + save_name(branch, utc) + b'\n')
        elif not keep_save:
            removals.append(save_name(branch, utc))

if not opt.pretend:
    die_if_errors()
    repo = LocalRepo()
    bup_rm(repo, removals, compression=opt.compress, verbosity=opt.verbose)
    if opt.gc:
        die_if_errors()
        bup_gc(threshold=opt.gc_threshold,
               compression=opt.compress,
               verbosity=opt.verbose)

die_if_errors()
