#!/usr/bin/env python
import sys, os, subprocess
import git
from helpers import *

argv = sys.argv
exe = argv[0]
exepath = os.path.split(exe)[0] or '.'

def usage():
    log('Usage: bup <subcmd> <options...>\n\n')
    log('Available subcommands:\n')
    for c in sorted(os.listdir(exepath)):
        if c.startswith('bup-') and c.find('.') < 0:
            log('\t%s\n' % c[4:])
    sys.exit(99)

if len(argv) < 2 or not argv[1] or argv[1][0] == '-':
    usage()

subcmd = argv[1]
if subcmd == 'help':
    usage()

def subpath(s):
    return os.path.join(exepath, 'bup-%s' % s)

if not os.path.exists(subpath(subcmd)):
    log('error: unknown command "%s"\n' % subcmd)
    usage()


already_fixed = atoi(os.environ.get('BUP_FORCE_TTY'))
if subcmd in ['ftp']:
    already_fixed = True
fix_stdout = not already_fixed and os.isatty(1)
fix_stderr = not already_fixed and os.isatty(2)

def force_tty():
    if fix_stdout or fix_stderr:
        os.environ['BUP_FORCE_TTY'] = '1'

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

ret = 95
try:
    try:
        p = subprocess.Popen([subpath(subcmd)] + argv[2:],
                             stdout=outf, stderr=errf, preexec_fn=force_tty)
        ret = p.wait()
    except OSError, e:
        log('%s: %s\n' % (subpath(subcmd), e))
        ret = 98
    except KeyboardInterrupt, e:
        ret = 94
finally:
    if n:
        n.stdin.close()
        try:
            n.wait()
        except:
            pass
sys.exit(ret)
