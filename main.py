#!/bin/sh
"""": # -*-python-*- # -*-python-*-
bup_python="$(dirname "$0")/cmd/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import, print_function
import errno, re, sys, os, subprocess, signal, getopt

if sys.version_info[0] != 2 \
   and not os.environ.get('BUP_ALLOW_UNEXPECTED_PYTHON_VERSION') == 'true':
    print('error: bup may crash with python versions other than 2, or eat your data',
          file=sys.stderr)
    sys.exit(2)

from subprocess import PIPE
from sys import stderr, stdout
import select

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
elif os.path.exists("%s/share/bup/cmd/." % exeprefix):
    # installed binary in /.../share.
    # eg. /usr/bin/bup means /usr/share/bup/... is where our libraries are.
    cmdpath = "%s/share/bup/cmd" % exeprefix
    libpath = "%s/share/bup" % exeprefix
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


from bup import compat, helpers
from bup.compat import add_ex_tb, add_ex_ctx, wrap_main
from bup.helpers import atoi, columnate, debug1, log, merge_dict, tty_width


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
except getopt.GetoptError as ex:
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

if fix_stdout or fix_stderr:
    tty_env = merge_dict(os.environ,
                         {'BUP_FORCE_TTY': str((fix_stdout and 1 or 0)
                                               + (fix_stderr and 2 or 0))})
else:
    tty_env = os.environ


sep_rx = re.compile(br'([\r\n])')

def print_clean_line(dest, content, width, sep=None):
    """Write some or all of content, followed by sep, to the dest fd after
    padding the content with enough spaces to fill the current
    terminal width or truncating it to the terminal width if sep is a
    carriage return."""
    global sep_rx
    assert sep in (b'\r', b'\n', None)
    if not content:
        if sep:
            os.write(dest, sep)
        return
    for x in content:
        assert not sep_rx.match(x)
    content = b''.join(content)
    if sep == b'\r' and len(content) > width:
        content = content[width:]
    os.write(dest, content)
    if len(content) < width:
        os.write(dest, b' ' * (width - len(content)))
    if sep:
        os.write(dest, sep)

def filter_output(src_out, src_err, dest_out, dest_err):
    """Transfer data from src_out to dest_out and src_err to dest_err via
    print_clean_line until src_out and src_err close."""
    global sep_rx
    assert not isinstance(src_out, bool)
    assert not isinstance(src_err, bool)
    assert not isinstance(dest_out, bool)
    assert not isinstance(dest_err, bool)
    assert src_out is not None or src_err is not None
    assert (src_out is None) == (dest_out is None)
    assert (src_err is None) == (dest_err is None)
    pending = {}
    pending_ex = None
    try:
        fds = tuple([x for x in (src_out, src_err) if x is not None])
        while fds:
            ready_fds, _, _ = select.select(fds, [], [])
            width = tty_width()
            for fd in ready_fds:
                buf = os.read(fd, 4096)
                dest = dest_out if fd == src_out else dest_err
                if not buf:
                    fds = tuple([x for x in fds if x is not fd])
                    print_clean_line(dest, pending.pop(fd, []), width)
                else:
                    split = sep_rx.split(buf)
                    while len(split) > 1:
                        content, sep = split[:2]
                        split = split[2:]
                        print_clean_line(dest,
                                         pending.pop(fd, []) + [content],
                                         width,
                                         sep)
                    assert(len(split) == 1)
                    if split[0]:
                        pending.setdefault(fd, []).extend(split)
    except BaseException as ex:
        pending_ex = add_ex_ctx(add_ex_tb(ex), pending_ex)
    try:
        # Try to finish each of the streams
        for fd, pending_items in compat.items(pending):
            dest = dest_out if fd == src_out else dest_err
            try:
                print_clean_line(dest, pending_items, width)
            except (EnvironmentError, EOFError) as ex:
                pending_ex = add_ex_ctx(add_ex_tb(ex), pending_ex)
    except BaseException as ex:
        pending_ex = add_ex_ctx(add_ex_tb(ex), pending_ex)
    if pending_ex:
        raise pending_ex

def run_subcmd(subcmd):

    c = (do_profile and [sys.executable, '-m', 'cProfile'] or []) + subcmd
    if not (fix_stdout or fix_stderr):
        os.execvp(c[0], c)

    p = None
    try:
        p = subprocess.Popen(c,
                             stdout=PIPE if fix_stdout else sys.stdout,
                             stderr=PIPE if fix_stderr else sys.stderr,
                             env=tty_env, bufsize=4096, close_fds=True)
        # Assume p will receive these signals and quit, which will
        # then cause us to quit.
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGQUIT):
            signal.signal(sig, signal.SIG_IGN)

        filter_output(fix_stdout and p.stdout.fileno() or None,
                      fix_stderr and p.stderr.fileno() or None,
                      fix_stdout and sys.stdout.fileno() or None,
                      fix_stderr and sys.stderr.fileno() or None)
        return p.wait()
    except BaseException as ex:
        add_ex_tb(ex)
        try:
            if p and p.poll() == None:
                os.kill(p.pid, signal.SIGTERM)
                p.wait()
        except BaseException as kill_ex:
            raise add_ex_ctx(add_ex_tb(kill_ex), ex)
        raise ex
        
wrap_main(lambda : run_subcmd(subcmd))
