#!/usr/bin/env python

from calendar import timegm
from pipes import quote
from subprocess import check_call, check_output
from time import strftime, strptime
import sys
import tempfile

from bup import git, options, vfs
from bup.helpers import handle_ctrl_c, log, saved_errors, unlink
import bup.path

optspec = """
bup import-duplicity [-n] <duplicity-source-url> <bup-save-name>
--
n,dry-run  don't do anything; just print what would be done
"""


def logcmd(cmd):
    if isinstance(cmd, basestring):
        log(cmd + '\n')
    else:
        log(' '.join(map(quote, cmd)) + '\n')


def exc(cmd, shell=False):
    global opt
    logcmd(cmd)
    if not opt.dry_run:
        check_call(cmd, shell=shell)

def exo(cmd, shell=False):
    global opt
    logcmd(cmd)
    if not opt.dry_run:
        return check_output(cmd, shell=shell)


handle_ctrl_c()

o = options.Options(optspec)
opt, flags, extra = o.parse(sys.argv[1:])

if len(extra) < 1 or not extra[0]:
    o.fatal('duplicity source URL required')
if len(extra) < 2 or not extra[1]:
    o.fatal('bup destination save name required')
if len(extra) > 2:
    o.fatal('too many arguments')

source_url, save_name = extra
bup = bup.path.exe()

git.check_repo_or_die()
top = vfs.RefList(None)

tmpdir = tempfile.mkdtemp(prefix='bup-import-dup-')
try:
    dup = ['duplicity', '--archive-dir', tmpdir + '/dup-cache']
    restoredir = tmpdir + '/restore'
    tmpidx = tmpdir + '/index'
    collection_status = \
        exo(' '.join(map(quote, dup))
            + ' collection-status --log-fd=3 %s 3>&1 1>&2' % quote(source_url),
            shell=True)
    # Duplicity output lines of interest look like this (one leading space):
    #  full 20150222T073111Z 1 noenc
    #  inc 20150222T073233Z 1 noenc
    dup_timestamps = []
    for line in collection_status.splitlines():
        if line.startswith(' inc '):
            assert(len(line) >= len(' inc 20150222T073233Z'))
            dup_timestamps.append(line[5:21])
        elif line.startswith(' full '):
            assert(len(line) >= len(' full 20150222T073233Z'))
            dup_timestamps.append(line[6:22])
    for i, dup_ts in enumerate(dup_timestamps):
        tm = strptime(dup_ts, '%Y%m%dT%H%M%SZ')
        exc(['rm', '-rf', restoredir])
        exc(dup + ['restore', '-t', dup_ts, source_url, restoredir])
        exc([bup, 'index', '-uxf', tmpidx, restoredir])
        exc([bup, 'save', '--strip', '--date', str(timegm(tm)), '-f', tmpidx,
             '-n', save_name, restoredir])
finally:
    exc(['rm', '-rf', tmpdir])

if saved_errors:
    log('warning: %d errors encountered\n' % len(saved_errors))
    sys.exit(1)
