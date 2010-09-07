#!/usr/bin/env python
import sys, os, subprocess, signal, getopt

argv = sys.argv
exe = argv[0]
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

from bup.helpers import *


def usage():
    log('Usage: bup [-?|--help] [-d=BUP_DIR|--bup-dir=BUP_DIR] COMMAND [ARGS]'
        + '\n\n')
    common = dict(
        ftp = 'Browse backup sets using an ftp-like client',
        fsck = 'Check backup sets for damage and add redundancy information',
        fuse = 'Mount your backup sets as a filesystem',
        help = 'Print detailed help for the given command',
        index = 'Create or display the index of files to back up',
        on = 'Backup a remote machine to the local one',
        save = 'Save files into a backup set (note: run "bup index" first)',
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
    sys.exit(99)


if len(argv) < 2:
    usage()

# Handle global options.
try:
    global_args, subcmd = getopt.getopt(argv[1:], '?Vd:',
                                        ['help', 'version', 'bup-dir='])
except getopt.GetoptError, ex:
    log('error: ' + ex.msg + '\n')
    usage()

help_requested = None
dest_dir = None

for opt in global_args:
    if opt[0] == '-?' or opt[0] == '--help':
        help_requested = True
    if opt[0] == '-V' or opt[0] == '--version':
        subcmd = ['version']
    elif opt[0] == '-d' or opt[0] == '--bup-dir':
        dest_dir = opt[1]
    else:
        log('error: unexpected option "%s"\n' % opt[0])
        usage()

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

subcmd_env = os.environ
if dest_dir:
    subcmd_env.update({"BUP_DIR" : dest_dir})

def subpath(s):
    sp = os.path.join(exepath, 'bup-%s' % s)
    if not os.path.exists(sp):
        sp = os.path.join(cmdpath, 'bup-%s' % s)
    return sp

if not os.path.exists(subpath(subcmd_name)):
    log('error: unknown command "%s"\n' % subcmd_name)
    usage()

already_fixed = atoi(os.environ.get('BUP_FORCE_TTY'))
if subcmd_name in ['ftp', 'help']:
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

ret = 95
p = None
try:
    try:
        p = subprocess.Popen([subpath(subcmd_name)] + subcmd[1:],
                             stdout=outf, stderr=errf, preexec_fn=force_tty)
        while 1:
            # if we get a signal while waiting, we have to keep waiting, just
            # in case our child doesn't die.
            try:
                ret = p.wait()
                break
            except SigException, e:
                log('\nbup: %s\n' % e)
                os.kill(p.pid, e.signum)
                ret = 94
    except OSError, e:
        log('%s: %s\n' % (subpath(subcmd_name), e))
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
