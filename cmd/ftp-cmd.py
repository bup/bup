#!/usr/bin/env python
import sys, os, re, stat, fnmatch
from bup import options, git, shquote, vfs
from bup.helpers import *

try:
    import readline
except ImportError:
    log('* readline module not available: line editing disabled.\n')
    readline = None


def node_name(text, n):
    if stat.S_ISDIR(n.mode):
        return '%s/' % text
    elif stat.S_ISLNK(n.mode):
        return '%s@' % text
    else:
        return '%s' % text


def do_ls(path, n):
    l = []
    if stat.S_ISDIR(n.mode):
        for sub in n:
            l.append(node_name(sub.name, sub))
    else:
        l.append(node_name(path, n))
    print columnate(l, '')
    

def write_to_file(inf, outf):
    for blob in chunkyreader(inf):
        outf.write(blob)
    

def inputiter():
    if os.isatty(sys.stdin.fileno()):
        while 1:
            try:
                yield raw_input('bup> ')
            except EOFError:
                break
    else:
        for line in sys.stdin:
            yield line


def _completer_get_subs(line):
    (qtype, lastword) = shquote.unfinished_word(line)
    (dir,name) = os.path.split(lastword)
    #log('\ncompleter: %r %r %r\n' % (qtype, lastword, text))
    n = pwd.resolve(dir)
    subs = list(filter(lambda x: x.name.startswith(name),
                       n.subs()))
    return (dir, name, qtype, lastword, subs)


_last_line = None
_last_res = None
def completer(text, state):
    global _last_line
    global _last_res
    try:
        line = readline.get_line_buffer()[:readline.get_endidx()]
        if _last_line != line:
            _last_res = _completer_get_subs(line)
            _last_line = line
        (dir, name, qtype, lastword, subs) = _last_res
        if state < len(subs):
            sn = subs[state]
            sn1 = sn.resolve('')  # deref symlinks
            fullname = os.path.join(dir, sn.name)
            if stat.S_ISDIR(sn1.mode):
                ret = shquote.what_to_add(qtype, lastword, fullname+'/',
                                          terminate=False)
            else:
                ret = shquote.what_to_add(qtype, lastword, fullname,
                                          terminate=True) + ' '
            return text + ret
    except Exception, e:
        log('\nerror in completion: %s\n' % e)

            
optspec = """
bup ftp
"""
o = options.Options('bup ftp', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()

top = vfs.RefList(None)
pwd = top

if extra:
    lines = extra
else:
    if readline:
        readline.set_completer_delims(' \t\n\r/')
        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")
    lines = inputiter()

for line in lines:
    if not line.strip():
        continue
    words = [word for (wordstart,word) in shquote.quotesplit(line)]
    cmd = words[0].lower()
    #log('execute: %r %r\n' % (cmd, parm))
    try:
        if cmd == 'ls':
            for parm in (words[1:] or ['.']):
                do_ls(parm, pwd.resolve(parm))
        elif cmd == 'cd':
            for parm in words[1:]:
                pwd = pwd.resolve(parm)
        elif cmd == 'pwd':
            print pwd.fullname()
        elif cmd == 'cat':
            for parm in words[1:]:
                write_to_file(pwd.resolve(parm).open(), sys.stdout)
        elif cmd == 'get':
            if len(words) not in [2,3]:
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
                            log('  error: %s\n' % e)
        elif cmd == 'help' or cmd == '?':
            log('Commands: ls cd pwd cat get mget help quit\n')
        elif cmd == 'quit' or cmd == 'exit' or cmd == 'bye':
            break
        else:
            raise Exception('no such command %r' % cmd)
    except Exception, e:
        log('error: %s\n' % e)
        #raise
