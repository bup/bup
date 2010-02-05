#!/usr/bin/env python
import sys, os, git

argv = sys.argv
exe = argv[0]
exepath = os.path.split(exe)[0] or '.'

def log(s):
    sys.stderr.write(s)

def usage():
    log('Usage: %s <subcmd> <options...>\n\n' % exe)
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

subpath = os.path.join(exepath, 'bup-%s' % subcmd)

if not os.path.exists(subpath):
    log('%s: unknown command "%s"\n' % (exe, subcmd))
    usage()

try:
    os.execv(subpath, [subpath] + argv[2:])
except OSError, e:
    log('%s: %s\n' % (subpath, e))
    sys.exit(98)
