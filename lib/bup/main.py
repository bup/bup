
from __future__ import absolute_import, print_function

import bup_main, os, sys
if bup_main.env_pythonpath:
    if sys.version_info[0] < 3:
        os.environ['PYTHONPATH'] = bup_main.env_pythonpath
    else:
        os.environb[b'PYTHONPATH'] = bup_main.env_pythonpath
else:
    del os.environ['PYTHONPATH']

from contextlib import ExitStack
from importlib import import_module
from pkgutil import iter_modules
from subprocess import PIPE
from threading import Thread
import re, select, signal, subprocess

from bup import compat, path, helpers
from bup.compat import (
    environ,
    fsdecode,
    wrap_main
)
from bup.helpers import (
    columnate,
    finalized,
    handle_ctrl_c,
    log,
    tty_width
)
from bup.git import close_catpipes
from bup.io import byte_stream, path_msg
from bup.options import _tty_width
import bup.cmd

def maybe_import_early(argv):
    """Scan argv and import any modules specified by --import-py-module."""
    while argv:
        if argv[0] != '--import-py-module':
            argv = argv[1:]
            continue
        if len(argv) < 2:
            log("bup: --import-py-module must have an argument\n")
            exit(2)
        mod = argv[1]
        import_module(mod)
        argv = argv[2:]

maybe_import_early(compat.get_argv())

handle_ctrl_c()

cmdpath = path.cmddir()

# We manipulate the subcmds here as strings, but they must be ASCII
# compatible, since we're going to be looking for exactly
# b'bup-SUBCMD' to exec.

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
    cmds = set()
    for c in sorted(os.listdir(cmdpath)):
        if c.startswith(b'bup-') and c.find(b'.') < 0:
            cname = fsdecode(c[4:])
            if cname not in common:
                cmds.add(c[4:].decode(errors='backslashreplace'))
    # built-in commands take precedence
    for _, name, _ in iter_modules(path=bup.cmd.__path__):
        name = name.replace('_','-')
        if name not in common:
            cmds.add(name)

    log(columnate(sorted(cmds), '    '))
    log('\n')

    log("See 'bup help COMMAND' for more information on " +
        "a specific command.\n")
    if msg:
        log("\n%s\n" % msg)
    sys.exit(99)

def extract_argval(args):
    """Assume args (all elements bytes) starts with a -x, --x, or --x=,
argument that requires a value and return that value and the remaining
args.  Exit with an errror if the value is missing.

    """
    # Assumes that first arg is a valid arg
    arg = args[0]
    if b'=' in arg:
        val = arg.split(b'=')[1]
        if not val:
            usage('error: no value provided for %s option' % arg)
        return val, args[1:]
    if len(args) < 2:
        usage('error: no value provided for %s option' % arg)
    return args[1], args[2:]


args = compat.get_argvb()
if len(args) < 2:
    usage()

## Parse global options
help_requested = None
do_profile = False
bup_dir = None
args = args[1:]
subcmd = None
while args:
    arg = args[0]
    if arg in (b'-?', b'--help'):
        help_requested = True
        args = args[1:]
    elif arg in (b'-V', b'--version'):
        subcmd = [b'version']
        args = args[1:]
    elif arg in (b'-D', b'--debug'):
        helpers.buglvl += 1
        environ[b'BUP_DEBUG'] = b'%d' % helpers.buglvl
        args = args[1:]
    elif arg == b'--profile':
        do_profile = True
        args = args[1:]
    elif arg in (b'-d', b'--bup-dir') or arg.startswith(b'--bup-dir='):
        bup_dir, args = extract_argval(args)
    elif arg == b'--import-py-module' or arg.startswith(b'--import-py-module='):
        # Just need to skip it here
        _, args = extract_argval(args)
    elif arg.startswith(b'-'):
        usage('error: unexpected option "%s"'
              % arg.decode('ascii', 'backslashescape'))
    else:
        break

subcmd = subcmd or args

# Make BUP_DIR absolute, so we aren't affected by chdir (i.e. save -C, etc.).
if bup_dir:
    environ[b'BUP_DIR'] = os.path.abspath(bup_dir)

if len(subcmd) == 0:
    if help_requested:
        subcmd = [b'help']
    else:
        usage()

if help_requested and subcmd[0] != b'help':
    subcmd = [b'help'] + subcmd

if len(subcmd) > 1 and subcmd[1] == b'--help' and subcmd[0] != b'help':
    subcmd = [b'help', subcmd[0]] + subcmd[2:]

subcmd_name = subcmd[0]
if not subcmd_name:
    usage()

try:
    cmd_module_name = 'bup.cmd.' + subcmd_name.decode('ascii').replace('-', '_')
    cmd_module = import_module(cmd_module_name)
except ModuleNotFoundError as ex:
    if ex.name != cmd_module_name:
        raise ex
    cmd_module = None

if not cmd_module:
    subcmd[0] = os.path.join(cmdpath, b'bup-' + subcmd_name)
    if not os.path.exists(subcmd[0]):
        usage('error: unknown command "%s"' % path_msg(subcmd_name))

already_fixed = int(environ.get(b'BUP_FORCE_TTY', 0))
if subcmd_name in (b'mux', b'ftp', b'help', b'fuse'):
    fix_stdout = False
    fix_stderr = False
else:
    fix_stdout = not (already_fixed & 1) and os.isatty(1)
    fix_stderr = not (already_fixed & 2) and os.isatty(2)

if fix_stdout or fix_stderr:
    _ttymask = (fix_stdout and 1 or 0) + (fix_stderr and 2 or 0)
    environ[b'BUP_FORCE_TTY'] = b'%d' % _ttymask
    environ[b'BUP_TTY_WIDTH'] = b'%d' % _tty_width()


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
        content = content[:width]
    os.write(dest, content)
    if len(content) < width:
        os.write(dest, b' ' * (width - len(content)))
    if sep:
        os.write(dest, sep)

# FIXME: check whether we might need to stash/defer exceptions while
# stderr is diverted.

def filter_output(srcs, dests, control):
    """Transfer data from file descriptors in srcs to the
    corresponding file descriptors in dests print_clean_line until the
    control descriptor produces a 'q' (i.e. quit).

    """
    assert all(isinstance(x, int) for x in srcs)
    assert all(isinstance(x, int) for x in dests)
    assert len(srcs) == len(dests)
    assert isinstance(control, int)
    read_fds = [control, *srcs]
    dest_for = dict(zip(srcs, dests))
    pending = {}
    try:
        while True:
            ready_fds, _, _ = select.select(read_fds, [], [])
            width = tty_width()
            for fd in ready_fds:
                if fd == control:
                    continue
                buf = os.read(fd, 4096)
                dest = dest_for[fd]
                split = sep_rx.split(buf)
                while len(split) > 1:
                    content, sep = split[:2]
                    split = split[2:]
                    print_clean_line(dest,
                                     pending.pop(fd, []) + [content],
                                     width,
                                     sep)
                assert len(split) == 1
                if split[0]:
                    pending.setdefault(fd, []).extend(split)
            if control in ready_fds:
                buf = os.read(control, 1)
                assert buf == b'q'
                break
    except BaseException as ex:
        pending_ex = ex
        # Try to finish each of the streams
        try:
            for fd, pending_items in pending.items():
                dest = dest_for[fd]
                width = tty_width()
                try:
                    print_clean_line(dest, pending_items, width)
                except (EnvironmentError, EOFError) as ex:
                    ex.__cause__ = pending_ex
                    pending_ex = ex
        finally:
            raise pending_ex

def import_and_run_main(module, args):
    if do_profile:
        import cProfile
        f = compile('module.main(args)', __file__, 'exec')
        cProfile.runctx(f, globals(), locals())
    else:
        module.main(args)


def run_module_cmd(module, args):
    if not (fix_stdout or fix_stderr):
        return import_and_run_main(module, args)
    # Interpose filter_output between all attempts to write to the
    # stdout/stderr and the real stdout/stderr (e.g. the fds that
    # connect directly to the terminal) via a thread that runs
    # filter_output in a pipeline.
    srcs = []
    dests = []
    real_out_fd = real_err_fd = stdout_pipe = stderr_pipe = None
    filter_thread = filter_thread_started = None
    try:
        with ExitStack() as after_join:
            def fix_stream(src):
                src.flush()
                pipe = os.pipe()  # monitored_by_filter, what_everyone_uses
                after_join.enter_context(finalized(lambda _: os.close(pipe[1])))
                real_fd = os.dup(src.fileno())
                os.dup2(pipe[1], src.fileno())
                # Restore stream so that we don't risk losing output
                fin = finalized(real_fd, lambda x: os.dup2(x, src.fileno()))
                after_join.enter_context(fin)
                srcs.append(pipe[0])
                dests.append(real_fd)
            if fix_stdout: fix_stream(sys.stdout)
            if fix_stderr: fix_stream(sys.stderr)
            ctrl_pipe = os.pipe()
            filter_thread_ex = None
            def run():
                nonlocal filter_thread_ex
                try:
                    filter_output(srcs, dests, ctrl_pipe[0])
                except BaseException as ex:
                    filter_thread_ex = ex
            filter_thread = Thread(name='output filter', target=run)
            filter_thread.start()
            try:
                result = import_and_run_main(module, args)
                # main may sys.exit(), so don't put anything that matters here
            finally:
                os.write(ctrl_pipe[1], b'q')
                filter_thread.join()
                if filter_thread_ex:
                    raise filter_thread_ex
    finally:
        close_catpipes()
    return result


def run_subproc_cmd(args):

    c = (do_profile and [sys.executable, b'-m', b'cProfile'] or []) + args
    if not (fix_stdout or fix_stderr):
        os.execvp(c[0], c)

    sys.stdout.flush()
    sys.stderr.flush()
    out = byte_stream(sys.stdout)
    err = byte_stream(sys.stderr)
    p = None
    try:
        p = subprocess.Popen(c,
                             stdout=PIPE if fix_stdout else out,
                             stderr=PIPE if fix_stderr else err,
                             bufsize=4096, close_fds=True)
        # Assume p will receive these signals and quit, which will
        # then cause us to quit.
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGQUIT):
            signal.signal(sig, signal.SIG_IGN)

        srcs = []
        dests = []
        if fix_stdout:
            srcs.append(p.stdout.fileno())
            dests.append(out.fileno())
        if fix_stderr:
            srcs.append(p.stderr.fileno())
            dests.append(err.fileno())
        filter_output(srcs, dests)
        return p.wait()
    except BaseException as ex:
        if p and p.poll() == None:
            os.kill(p.pid, signal.SIGTERM)
            p.wait()
        raise


def run_subcmd(module, args):
    if module:
        run_module_cmd(module, args)
    else:
        run_subproc_cmd(args)

def main():
    wrap_main(lambda : run_subcmd(cmd_module, subcmd))

if __name__ == "__main__":
    main()
