
import bup_main, os, sys
if bup_main.env_pythonpath:
    os.environb[b'PYTHONPATH'] = bup_main.env_pythonpath
else:
    del os.environ['PYTHONPATH']

from importlib import import_module
from os import fsdecode
from pkgutil import iter_modules

from bup import compat, io, path
from bup.compat import environ, print_exception
from bup.git import close_catpipes
from bup.helpers import \
    (EXIT_FAILURE,
     EXIT_SUCCESS,
     columnate,
     die_if_errors,
     handle_ctrl_c,
     log,
     progress)
from bup.io import path_msg
import bup.cmd

def maybe_import_early(argv):
    """Scan argv and import any modules specified by --import-py-module."""
    while argv:
        if argv[0] != '--import-py-module':
            argv = argv[1:]
            continue
        if len(argv) < 2:
            log("bup: --import-py-module must have an argument\n")
            exit(EXIT_FAILURE)
        mod = argv[1]
        import_module(mod)
        argv = argv[2:]

maybe_import_early(compat.get_argv())

handle_ctrl_c()

cmdpath = path.cmddir()

# We manipulate the subcmds here as strings, but they must be ASCII
# compatible, since we're going to be looking for exactly
# b'bup-SUBCMD' to exec.

def usage(file=sys.stdout):
    print('Usage: bup [-?|-h|--help] [-d BUP_DIR] [--debug] [--profile] '
          '<command> [options...]\n', file=file)
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

    print('Common commands:\n', file=file)
    for cmd,synopsis in sorted(common.items()):
        print('    %-10s %s' % (cmd, synopsis), file=file)
    print(file=file)

    print('Other available commands:', file=file)
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

    print(columnate(sorted(cmds), '    '), file=file)

    print("See 'bup help COMMAND' for more information on specific command.",
          file=file)

def misuse(msg=None):
    usage(file=sys.stderr)
    if msg:
        print(f'\n{msg}', file=sys.stderr)
    sys.exit(EXIT_FAILURE)

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
            misuse(f'error: no value provided for {arg} option')
        return val, args[1:]
    if len(args) < 2:
        misuse(f'error: no value provided for {arg} option')
    return args[1], args[2:]

args = compat.get_argvb()

if len(args) == 2 and args[1] in (b'-?', b'-h', b'--help'):
    usage()
    sys.exit(EXIT_SUCCESS)

if len(args) == 1:
    misuse()

## Parse global options
do_profile = False
bup_dir = None
args = args[1:]
subcmd = None
while args:
    arg = args[0]
    if arg in (b'-?', b'-h', b'--help'):
        misuse()
    elif arg in (b'-V', b'--version'):
        subcmd = [b'version']
        args = args[1:]
    elif arg in (b'-D', b'--debug'):
        io.buglvl += 1
        environ[b'BUP_DEBUG'] = b'%d' % io.buglvl
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
        misuse('error: unexpected option "%s"'
               % arg.decode('ascii', 'backslashescape'))
    else:
        break

subcmd = subcmd or args

# It's important that we defer initialization/use of the repo to the
# subcommands because they may select another (e.g. "bup init REPO").
if bup_dir:
    # Make BUP_DIR absolute, so we aren't affected by chdir (i.e. save
    # -C, etc.).
    environ[b'BUP_DIR'] = os.path.abspath(bup_dir)

if len(subcmd) == 0:
    misuse()

if len(subcmd) > 1 and subcmd[1] == b'--help' and subcmd[0] != b'help':
    subcmd = [b'help', subcmd[0]] + subcmd[2:]

subcmd_name = subcmd[0]
if not subcmd_name:
    misuse()

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
        misuse(f'error: unknown command {path_msg(subcmd_name)!r}')

def run_subcmd(module, args):
    # We may want to revisit these later, but for now, do what we've
    # always done (also wrt older servers).
    already_fixed = int(environ.get(b'BUP_FORCE_TTY', 0))
    if (not already_fixed) and subcmd not in (b'mux', b'ftp', b'help', b'fuse'):
        fix_stdout = not (already_fixed & 1) and os.isatty(1)
        fix_stderr = not (already_fixed & 2) and os.isatty(2)
        if fix_stdout or fix_stderr:
            _ttymask = (fix_stdout and 1 or 0) + (fix_stderr and 2 or 0)
            environ[b'BUP_FORCE_TTY'] = b'%d' % _ttymask
    if module:
        try:
            if not do_profile:
                return module.main(args)
            import cProfile
            f = compile('module.main(args)', __file__, 'exec')
            return cProfile.runctx(f, globals(), locals())
        finally:
            try:
                # clear before exit so next process won't intermingle
                progress('')
            finally:
                close_catpipes()
    # FIXME: when would do_profile make sense here anymore?
    args = (do_profile and [sys.executable, b'-m', b'cProfile'] or []) + args
    os.execvp(args[0], args)
    assert False, 'unreachable'  # pylint (e.g. 3.3.3)
    return None  # pylint (older, e.g. 2.2.2)

def main():
    try:
        rc = run_subcmd(cmd_module, subcmd)
    except KeyboardInterrupt:
        rc = 130
    except SystemExit as ex:
        raise ex
    except BaseException as ex:
        print_exception(ex)
        rc = EXIT_FAILURE
    if rc:
        sys.exit(rc)
    die_if_errors()

if __name__ == "__main__":
    main()
