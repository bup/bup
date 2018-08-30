#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import, print_function
import sys, os, stat, fnmatch

from bup import options, git, shquote, ls, vfs
from bup.helpers import chunkyreader, handle_ctrl_c, log
from bup.repo import LocalRepo

handle_ctrl_c()


class OptionError(Exception):
    pass


def do_ls(repo, args):
    try:
        opt = ls.opts_from_cmdline(args, onabort=OptionError)
    except OptionError as e:
        log('error: %s' % e)
        return
    return ls.within_repo(repo, opt)


def write_to_file(inf, outf):
    for blob in chunkyreader(inf):
        outf.write(blob)


def inputiter():
    if os.isatty(sys.stdin.fileno()):
        while 1:
            try:
                yield raw_input('bup> ')
            except EOFError:
                print()  # Clear the line for the terminal's next prompt
                break
    else:
        for line in sys.stdin:
            yield line


def _completer_get_subs(repo, line):
    (qtype, lastword) = shquote.unfinished_word(line)
    (dir,name) = os.path.split(lastword)
    dir_path = vfs.resolve(repo, dir or '/')
    _, dir_item = dir_path[-1]
    if not dir_item:
        subs = tuple()
    else:
        subs = tuple(dir_path + (entry,)
                     for entry in vfs.contents(repo, dir_item)
                     if (entry[0] != '.' and entry[0].startswith(name)))
    return dir, name, qtype, lastword, subs


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
def completer(text, iteration):
    global repo
    global _last_line
    global _last_res
    global rl_completion_suppress_append
    if rl_completion_suppress_append is not None:
        rl_completion_suppress_append.value = 1
    try:
        line = readline.get_line_buffer()[:readline.get_endidx()]
        if _last_line != line:
            _last_res = _completer_get_subs(repo, line)
            _last_line = line
        (dir, name, qtype, lastword, subs) = _last_res
        if iteration < len(subs):
            path = subs[iteration]
            leaf_name, leaf_item = path[-1]
            res = vfs.try_resolve(repo, leaf_name, parent=path[:-1])
            leaf_name, leaf_item = res[-1]
            fullname = os.path.join(*(name for name, item in res))
            if stat.S_ISDIR(vfs.item_mode(leaf_item)):
                ret = shquote.what_to_add(qtype, lastword, fullname+'/',
                                          terminate=False)
            else:
                ret = shquote.what_to_add(qtype, lastword, fullname,
                                          terminate=True) + ' '
            return text + ret
    except Exception as e:
        log('\n')
        try:
            import traceback
            traceback.print_tb(sys.exc_traceback)
        except Exception as e2:
            log('Error printing traceback: %s\n' % e2)
        log('\nError in completion: %s\n' % e)


optspec = """
bup ftp [commands...]
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()

repo = LocalRepo()
pwd = vfs.resolve(repo, '/')
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
            # MacOS uses a slightly incompatible clone of libreadline
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
            # FIXME: respect pwd (perhaps via ls accepting resolve path/parent)
            do_ls(repo, words[1:])
        elif cmd == 'cd':
            np = pwd
            for parm in words[1:]:
                res = vfs.resolve(repo, parm, parent=np)
                _, leaf_item = res[-1]
                if not leaf_item:
                    raise Exception('%r does not exist'
                                    % '/'.join(name for name, item in res))
                if not stat.S_ISDIR(vfs.item_mode(leaf_item)):
                    raise Exception('%r is not a directory' % parm)
                np = res
            pwd = np
        elif cmd == 'pwd':
            if len(pwd) == 1:
                sys.stdout.write('/')
            print('/'.join(name for name, item in pwd))
        elif cmd == 'cat':
            for parm in words[1:]:
                res = vfs.resolve(repo, parm, parent=pwd)
                _, leaf_item = res[-1]
                if not leaf_item:
                    raise Exception('%r does not exist' %
                                    '/'.join(name for name, item in res))
                with vfs.fopen(repo, leaf_item) as srcfile:
                    write_to_file(srcfile, sys.stdout)
        elif cmd == 'get':
            if len(words) not in [2,3]:
                rv = 1
                raise Exception('Usage: get <filename> [localname]')
            rname = words[1]
            (dir,base) = os.path.split(rname)
            lname = len(words)>2 and words[2] or base
            res = vfs.resolve(repo, rname, parent=pwd)
            _, leaf_item = res[-1]
            if not leaf_item:
                raise Exception('%r does not exist' %
                                '/'.join(name for name, item in res))
            with vfs.fopen(repo, leaf_item) as srcfile:
                with open(lname, 'wb') as destfile:
                    log('Saving %r\n' % lname)
                    write_to_file(srcfile, destfile)
        elif cmd == 'mget':
            for parm in words[1:]:
                (dir,base) = os.path.split(parm)

                res = vfs.resolve(repo, dir, parent=pwd)
                _, dir_item = res[-1]
                if not dir_item:
                    raise Exception('%r does not exist' % dir)
                for name, item in vfs.contents(repo, dir_item):
                    if name == '.':
                        continue
                    if fnmatch.fnmatch(name, base):
                        if stat.S_ISLNK(vfs.item_mode(item)):
                            deref = vfs.resolve(repo, name, parent=res)
                            deref_name, deref_item = deref[-1]
                            if not deref_item:
                                raise Exception('%r does not exist' %
                                                '/'.join(name for name, item
                                                         in deref))
                            item = deref_item
                        with vfs.fopen(repo, item) as srcfile:
                            with open(name, 'wb') as destfile:
                                log('Saving %r\n' % name)
                                write_to_file(srcfile, destfile)
        elif cmd == 'help' or cmd == '?':
            # FIXME: move to stdout
            log('Commands: ls cd pwd cat get mget help quit\n')
        elif cmd in ('quit', 'exit', 'bye'):
            break
        else:
            rv = 1
            raise Exception('no such command %r' % cmd)
    except Exception as e:
        rv = 1
        log('error: %s\n' % e)
        raise

sys.exit(rv)
