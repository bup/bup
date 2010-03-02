#!/usr/bin/env python
import sys, os, subprocess, signal

argv = sys.argv
exe = argv[0]
exepath = os.path.split(exe)[0] or '.'

# fix the PYTHONPATH to include our lib dir
libpath = os.path.join(exepath, 'lib')
cmdpath = os.path.join(exepath, 'cmd')
sys.path[:0] = [libpath]
os.environ['PYTHONPATH'] = libpath + ':' + os.environ.get('PYTHONPATH', '')

from bup.helpers import *


def columnate(l, prefix):
    l = l[:]
    clen = max(len(s) for s in l)
    ncols = (78 - len(prefix)) / (clen + 2)
    if ncols <= 1:
        ncols = 1
        clen = 0
    cols = []
    while len(l) % ncols:
        l.append('')
    rows = len(l)/ncols
    for s in range(0, len(l), rows):
        cols.append(l[s:s+rows])
    for row in zip(*cols):
        print prefix + ''.join(('%-*s' % (clen+2, s)) for s in row)


def usage():
    log('Usage: bup <command> <options...>\n\n')
    common = dict(
        ftp = 'Browse backup sets using an ftp-like client',
        fsck = 'Check backup sets for damage and add redundancy information',
        fuse = 'Mount your backup sets as a filesystem',
        help = 'Print detailed help for the given command',
        index = 'Create or display the index of files to back up',
        join = 'Retrieve a file backed up using "bup split"',
        ls = 'Browse the files in your backup sets',
        midx = 'Index objects to speed up future backups',
        save = 'Save files into a backup set (note: run "bup index" first)',
        split = 'Split a single file into its own backup set',
    )

    log('Common commands:\n')
    for cmd,synopsis in sorted(common.items()):
        print '    %-10s %s' % (cmd, synopsis)
    log('\n')
    
    log('Other available commands:\n')
    cmds = []
    for c in sorted(os.listdir(cmdpath) + os.listdir(exepath)):
        if c.startswith('bup-') and c.find('.') < 0:
            cname = c[4:]
            if cname not in common:
                cmds.append(c[4:])
    columnate(cmds, '    ')
    log('\n')
    
    log("See 'bup help <command>' for more information on " +
        "a specific command.\n")
    sys.exit(99)


if len(argv) < 2 or not argv[1] or argv[1][0] == '-':
    usage()

subcmd = argv[1]

def subpath(s):
    sp = os.path.join(exepath, 'bup-%s' % s)
    if not os.path.exists(sp):
        sp = os.path.join(cmdpath, 'bup-%s' % s)
    return sp

if not os.path.exists(subpath(subcmd)):
    log('error: unknown command "%s"\n' % subcmd)
    usage()


already_fixed = atoi(os.environ.get('BUP_FORCE_TTY'))
if subcmd in ['ftp', 'help']:
    already_fixed = True
fix_stdout = not already_fixed and os.isatty(1)
fix_stderr = not already_fixed and os.isatty(2)

def force_tty():
    if fix_stdout or fix_stderr:
        amt = (fix_stdout and 1 or 0) + (fix_stderr and 2 or 0)
        os.environ['BUP_FORCE_TTY'] = str(amt)

if fix_stdout or fix_stderr:
    realf = fix_stderr and 2 or 1
    n = subprocess.Popen([subpath('newliner')],
                         stdin=subprocess.PIPE, stdout=os.dup(realf),
                         close_fds=True, preexec_fn=force_tty)
    outf = fix_stdout and n.stdin.fileno() or 1
    errf = fix_stderr and n.stdin.fileno() or 2
else:
    n = None
    outf = 1
    errf = 2


class SigException(Exception):
    pass
def handler(signum, frame):
    raise SigException('signal %d received' % signum)

signal.signal(signal.SIGTERM, handler)
signal.signal(signal.SIGINT, handler)

ret = 95
try:
    try:
        p = subprocess.Popen([subpath(subcmd)] + argv[2:],
                             stdout=outf, stderr=errf, preexec_fn=force_tty)
        ret = p.wait()
    except OSError, e:
        log('%s: %s\n' % (subpath(subcmd), e))
        ret = 98
    except SigException, e:
        ret = 94
finally:
    if p and p.poll() == None:
        os.kill(p.pid, signal.SIGTERM)
        p.wait()
    if n:
        n.stdin.close()
        try:
            n.wait()
        except:
            pass
sys.exit(ret)
