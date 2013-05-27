#!/usr/bin/env python
import sys, os, stat, fnmatch
from bup import options, git, shquote, vfs, ls
from bup.helpers import *

handle_ctrl_c()


class OptionError(Exception):
    pass


# Check out lib/bup/ls.py for the opt spec
def do_ls(cmd_args):
    try:
        ls.do_ls(cmd_args, pwd, onabort=OptionError)
    except OptionError, e:
        return


def write_to_file(inf, outf):
    for blob in chunkyreader(inf):
        outf.write(blob)


def inputiter():
    if os.isatty(sys.stdin.fileno()):
        while 1:
            try:
                yield raw_input('bup> ')
            except EOFError:
                print ''  # Clear the line for the terminal's next prompt
                break
    else:
        for line in sys.stdin:
            yield line


def _completer_get_subs(line):
    (qtype, lastword) = shquote.unfinished_word(line)
    (dir,name) = os.path.split(lastword)
    #log('\ncompleter: %r %r %r\n' % (qtype, lastword, text))
    try:
        n = pwd.resolve(dir)
        subs = list(filter(lambda x: x.name.startswith(name),
                           n.subs()))
    except vfs.NoSuchFile, e:
        subs = []
    return (dir, name, qtype, lastword, subs)


def find_readline_lib():
    """Return the name (and possibly the full path) of the readline library
    linked to the given readline module.
    """
    import readline
    f = open(readline.__file__, "rb")
    try:
        data = f.read()
    finally:
        f.close()
    import re
    m = re.search('\0([^\0]*libreadline[^\0]*)\0', data)
    if m:
        return m.group(1)
    return None


def init_readline_vars():
    """Work around trailing space automatically inserted by readline.
    See http://bugs.python.org/issue5833"""
    try:
        import ctypes
    except ImportError:
        # python before 2.5 didn't have the ctypes module; but those
        # old systems probably also didn't have this readline bug, so
        # just ignore it.
        return
    lib_name = find_readline_lib()
    if lib_name is not None:
        lib = ctypes.cdll.LoadLibrary(lib_name)
        global rl_completion_suppress_append
        rl_completion_suppress_append = ctypes.c_int.in_dll(lib,
                                    "rl_completion_suppress_append")


rl_completion_suppress_append = None
_last_line = None
_last_res = None
def completer(text, state):
    global _last_line
    global _last_res
    global rl_completion_suppress_append
    if rl_completion_suppress_append is not None:
        rl_completion_suppress_append.value = 1
    try:
        line = readline.get_line_buffer()[:readline.get_endidx()]
        if _last_line != line:
            _last_res = _completer_get_subs(line)
            _last_line = line
        (dir, name, qtype, lastword, subs) = _last_res
        if state < len(subs):
            sn = subs[state]
            sn1 = sn.try_resolve()  # find the type of any symlink target
            fullname = os.path.join(dir, sn.name)
            if stat.S_ISDIR(sn1.mode):
                ret = shquote.what_to_add(qtype, lastword, fullname+'/',
                                          terminate=False)
            else:
                ret = shquote.what_to_add(qtype, lastword, fullname,
                                          terminate=True) + ' '
            return text + ret
    except Exception, e:
        log('\n')
        try:
            import traceback
            traceback.print_tb(sys.exc_traceback)
        except Exception, e2:
            log('Error printing traceback: %s\n' % e2)
        log('\nError in completion: %s\n' % e)


optspec = """
bup ftp [commands...]
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()

top = vfs.RefList(None)
pwd = top
rv = 0

if extra:
    lines = extra
else:
    try:
        import readline
    except ImportError:
        log('* readline module not available: line editing disabled.\n')
        readline = None

    if readline:
        readline.set_completer_delims(' \t\n\r/')
        readline.set_completer(completer)
        if sys.platform.startswith('darwin'):
            # MacOS uses a slighly incompatible clone of libreadline
            readline.parse_and_bind('bind ^I rl_complete')
        readline.parse_and_bind('tab: complete')
        init_readline_vars()
    lines = inputiter()

for line in lines:
    if not line.strip():
        continue
    words = [word for (wordstart,word) in shquote.quotesplit(line)]
    cmd = words[0].lower()
    #log('execute: %r %r\n' % (cmd, parm))
    try:
        if cmd == 'ls':
            do_ls(words[1:])
        elif cmd == 'cd':
            np = pwd
            for parm in words[1:]:
                np = np.resolve(parm)
                if not stat.S_ISDIR(np.mode):
                    raise vfs.NotDir('%s is not a directory' % parm)
            pwd = np
        elif cmd == 'pwd':
            print pwd.fullname()
        elif cmd == 'cat':
            for parm in words[1:]:
                write_to_file(pwd.resolve(parm).open(), sys.stdout)
        elif cmd == 'get':
            if len(words) not in [2,3]:
                rv = 1
                raise Exception('Usage: get <filename> [localname]')
            rname = words[1]
            (dir,base) = os.path.split(rname)
            lname = len(words)>2 and words[2] or base
            inf = pwd.resolve(rname).open()
            log('Saving %r\n' % lname)
            write_to_file(inf, open(lname, 'wb'))
        elif cmd == 'mget':
            for parm in words[1:]:
                (dir,base) = os.path.split(parm)
                for n in pwd.resolve(dir).subs():
                    if fnmatch.fnmatch(n.name, base):
                        try:
                            log('Saving %r\n' % n.name)
                            inf = n.open()
                            outf = open(n.name, 'wb')
                            write_to_file(inf, outf)
                            outf.close()
                        except Exception, e:
                            rv = 1
                            log('  error: %s\n' % e)
        elif cmd == 'help' or cmd == '?':
            log('Commands: ls cd pwd cat get mget help quit\n')
        elif cmd == 'quit' or cmd == 'exit' or cmd == 'bye':
            break
        else:
            rv = 1
            raise Exception('no such command %r' % cmd)
    except Exception, e:
        rv = 1
        log('error: %s\n' % e)
        #raise

sys.exit(rv)
