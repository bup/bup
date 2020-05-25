#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
from calendar import timegm
from pipes import quote
from subprocess import check_call
from time import strftime, strptime
import os
import sys
import tempfile

from bup import git, helpers, options
from bup.compat import argv_bytes, str_type
from bup.helpers import (handle_ctrl_c,
                         log,
                         readpipe,
                         shstr,
                         saved_errors,
                         unlink)
import bup.path

optspec = """
bup import-duplicity [-n] <duplicity-source-url> <bup-save-name>
--
n,dry-run  don't do anything; just print what would be done
"""

def logcmd(cmd):
    log(shstr(cmd).decode('iso-8859-1', errors='replace') + '\n')

def exc(cmd, shell=False):
    global opt
    logcmd(cmd)
    if not opt.dry_run:
        check_call(cmd, shell=shell)

def exo(cmd, shell=False, preexec_fn=None, close_fds=True):
    global opt
    logcmd(cmd)
    if not opt.dry_run:
        return helpers.exo(cmd, shell=shell, preexec_fn=preexec_fn,
                           close_fds=close_fds)[0]

def redirect_dup_output():
    os.dup2(1, 3)
    os.dup2(1, 2)


handle_ctrl_c()

log('\nbup: import-duplicity is EXPERIMENTAL (proceed with caution)\n\n')

o = options.Options(optspec)
opt, flags, extra = o.parse(sys.argv[1:])

if len(extra) < 1 or not extra[0]:
    o.fatal('duplicity source URL required')
if len(extra) < 2 or not extra[1]:
    o.fatal('bup destination save name required')
if len(extra) > 2:
    o.fatal('too many arguments')

source_url, save_name = extra
source_url = argv_bytes(source_url)
save_name = argv_bytes(save_name)
bup = bup.path.exe()

git.check_repo_or_die()

tmpdir = tempfile.mkdtemp(prefix=b'bup-import-dup-')
try:
    dup = [b'duplicity', b'--archive-dir', tmpdir + b'/dup-cache']
    restoredir = tmpdir + b'/restore'
    tmpidx = tmpdir + b'/index'

    collection_status = \
        exo(dup + [b'collection-status', b'--log-fd=3', source_url],
            close_fds=False, preexec_fn=redirect_dup_output)  # i.e. 3>&1 1>&2
    # Duplicity output lines of interest look like this (one leading space):
    #  full 20150222T073111Z 1 noenc
    #  inc 20150222T073233Z 1 noenc
    dup_timestamps = []
    for line in collection_status.splitlines():
        if line.startswith(b' inc '):
            assert(len(line) >= len(b' inc 20150222T073233Z'))
            dup_timestamps.append(line[5:21])
        elif line.startswith(b' full '):
            assert(len(line) >= len(b' full 20150222T073233Z'))
            dup_timestamps.append(line[6:22])
    for i, dup_ts in enumerate(dup_timestamps):
        tm = strptime(dup_ts.decode('ascii'), '%Y%m%dT%H%M%SZ')
        exc([b'rm', b'-rf', restoredir])
        exc(dup + [b'restore', b'-t', dup_ts, source_url, restoredir])
        exc([bup, b'index', b'-uxf', tmpidx, restoredir])
        exc([bup, b'save', b'--strip', b'--date', b'%d' % timegm(tm),
             b'-f', tmpidx, b'-n', save_name, restoredir])
    sys.stderr.flush()
finally:
    exc([b'rm', b'-rf', tmpdir])

if saved_errors:
    log('warning: %d errors encountered\n' % len(saved_errors))
    sys.exit(1)
