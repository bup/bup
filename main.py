#!/usr/bin/env python
import sys, os, subprocess, signal, getopt

argv = sys.argv
exe = os.path.realpath(argv[0])
exepath = os.path.split(exe)[0] or '.'
exeprefix = os.path.split(os.path.abspath(exepath))[0]

# fix the PYTHONPATH to include our lib dir
if os.path.exists("%s/lib/bup/cmd/." % exeprefix):
    # installed binary in /.../bin.
    # eg. /usr/bin/bup means /usr/lib/bup/... is where our libraries are.
    cmdpath = "%s/lib/bup/cmd" % exeprefix
    libpath = "%s/lib/bup" % exeprefix
    resourcepath = libpath
else:
    # running from the src directory without being installed first
    cmdpath = os.path.join(exepath, 'cmd')
    libpath = os.path.join(exepath, 'lib')
    resourcepath = libpath
sys.path[:0] = [libpath]
os.environ['PYTHONPATH'] = libpath + ':' + os.environ.get('PYTHONPATH', '')
os.environ['BUP_MAIN_EXE'] = os.path.abspath(exe)
os.environ['BUP_RESOURCE_PATH'] = resourcepath

from bup import helpers
from bup.helpers import *

# after running 'bup newliner', the tty_width() ioctl won't work anymore
os.environ['WIDTH'] = str(tty_width())

def usage(msg=""):
    log('Usage: bup [-?|--help] [-d BUP_DIR] [--debug] [--profile] '
        '<command> [options...]\n\n')
    common = dict(
        ftp = 'Browse backup sets using an ftp-like client',
        fsck = 'Check backup sets for damage and add redundancy information',
        fuse = 'Mount your backup sets as a filesystem',
        help = 'Print detailed help for the given command',
        index = 'Create or display the index of files to back up',
        on = 'Backup a remote machine to the local one',
        restore = 'Extract files from a backup set',
        save = 'Save files into a backup set (note: run "bup index" first)',
        tag = 'Tag commits for easier access',
        web = 'Launch a web server to examine backup sets',
    )

    log('Common commands:\n')
    for cmd,synopsis in sorted(common.items()):
        log('    %-10s %s\n' % (cmd, synopsis))
    log('\n')
    
    log('Other available commands:\n')
    cmds = []
    for c in sorted(os.listdir(cmdpath) + os.listdir(exepath)):
        if c.startswith('bup-') and c.find('.') < 0:
            cname = c[4:]
            if cname not in common:
                cmds.append(c[4:])
    log(columnate(cmds, '    '))
    log('\n')
    
    log("See 'bup help COMMAND' for more information on " +
        "a specific command.\n")
    if msg:
        log("\n%s\n" % msg)
    sys.exit(99)


if len(argv) < 2:
    usage()

# Handle global options.
try:
    optspec = ['help', 'version', 'debug', 'profile', 'bup-dir=']
    global_args, subcmd = getopt.getopt(argv[1:], '?VDd:', optspec)
except getopt.GetoptError, ex:
    usage('error: %s' % ex.msg)

help_requested = None
do_profile = False

for opt in global_args:
    if opt[0] in ['-?', '--help']:
        help_requested = True
    elif opt[0] in ['-V', '--version']:
        subcmd = ['version']
    elif opt[0] in ['-D', '--debug']:
        helpers.buglvl += 1
        os.environ['BUP_DEBUG'] = str(helpers.buglvl)
    elif opt[0] in ['--profile']:
        do_profile = True
    elif opt[0] in ['-d', '--bup-dir']:
        os.environ['BUP_DIR'] = opt[1]
    else:
        usage('error: unexpected option "%s"' % opt[0])

# Make BUP_DIR absolute, so we aren't affected by chdir (i.e. save -C, etc.).
if 'BUP_DIR' in os.environ:
    os.environ['BUP_DIR'] = os.path.abspath(os.environ['BUP_DIR'])

if len(subcmd) == 0:
    if help_requested:
        subcmd = ['help']
    else:
        usage()

if help_requested and subcmd[0] != 'help':
    subcmd = ['help'] + subcmd

if len(subcmd) > 1 and subcmd[1] == '--help' and subcmd[0] != 'help':
    subcmd = ['help', subcmd[0]] + subcmd[2:]

subcmd_name = subcmd[0]
if not subcmd_name:
    usage()

def subpath(s):
    sp = os.path.join(exepath, 'bup-%s' % s)
    if not os.path.exists(sp):
        sp = os.path.join(cmdpath, 'bup-%s' % s)
    return sp

subcmd[0] = subpath(subcmd_name)
if not os.path.exists(subcmd[0]):
    usage('error: unknown command "%s"' % subcmd_name)

already_fixed = atoi(os.environ.get('BUP_FORCE_TTY'))
if subcmd_name in ['mux', 'ftp', 'help']:
    already_fixed = True
fix_stdout = not already_fixed and os.isatty(1)
fix_stderr = not already_fixed and os.isatty(2)

def force_tty():
    if fix_stdout or fix_stderr:
        amt = (fix_stdout and 1 or 0) + (fix_stderr and 2 or 0)
        os.environ['BUP_FORCE_TTY'] = str(amt)
    os.setsid()  # make sure ctrl-c is sent just to us, not to child too

if fix_stdout or fix_stderr:
    realf = fix_stderr and 2 or 1
    drealf = os.dup(realf)  # Popen goes crazy with stdout=2
    n = subprocess.Popen([subpath('newliner')],
                         stdin=subprocess.PIPE, stdout=drealf,
                         close_fds=True, preexec_fn=force_tty)
    os.close(drealf)
    outf = fix_stdout and n.stdin.fileno() or None
    errf = fix_stderr and n.stdin.fileno() or None
else:
    n = None
    outf = None
    errf = None


class SigException(Exception):
    def __init__(self, signum):
        self.signum = signum
        Exception.__init__(self, 'signal %d received' % signum)
def handler(signum, frame):
    raise SigException(signum)

signal.signal(signal.SIGTERM, handler)
signal.signal(signal.SIGINT, handler)
signal.signal(signal.SIGTSTP, handler)
signal.signal(signal.SIGCONT, handler)

ret = 95
p = None
try:
    try:
        c = (do_profile and [sys.executable, '-m', 'cProfile'] or []) + subcmd
        if not n and not outf and not errf:
            # shortcut when no bup-newliner stuff is needed
            os.execvp(c[0], c)
        else:
            p = subprocess.Popen(c, stdout=outf, stderr=errf,
                                 preexec_fn=force_tty)
        while 1:
            # if we get a signal while waiting, we have to keep waiting, just
            # in case our child doesn't die.
            try:
                ret = p.wait()
                break
            except SigException, e:
                debug1('\nbup: %s\n' % e)
                sig = e.signum
                if sig == signal.SIGTSTP:
                    sig = signal.SIGSTOP
                os.kill(p.pid, sig)
                ret = 94
    except OSError, e:
        log('%s: %s\n' % (subcmd[0], e))
        ret = 98
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
