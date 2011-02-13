#!/usr/bin/env python
import sys, subprocess
from bup import git, options, client, path, index
from bup.helpers import *


optspec = """
bup juke -r host:path [filenames...]
--
r,remote=  remote repository path
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()
indexfile = git.repo('jukeindex')

if not opt.remote:
    o.fatal('you must provide the --remote option')
if not extra:
    o.fatal('at least one filename expected')

cli = client.Client(opt.remote)

rv = subprocess.call([path.exe(), 'index', '-u',
                      '--indexfile', indexfile, '--'] + extra)
if rv != 0:
    log('"bup index" returned error code %d\n' % rv)
    sys.exit(1)

rv = subprocess.call([path.exe(), 'save', '-t',
                      '-r', opt.remote,
                      '--indexfile', indexfile, '--'] + extra)
if rv != 0:
    log('"bup save" returned error code %d\n' % rv)
    sys.exit(1)

ix = index.Reader(indexfile)
cli.conn.write('jkstop\n')
cli.conn.check_ok()
count = 0
for ex in extra:
    # ix.filter returns entries in reverse alphabetical order; reverse it to
    # fix.
    for name,ent in reversed(list(ix.filter([ex]))):
        if name.endswith('/'):
            continue
        print name
        assert(ent.is_valid())
        cli.conn.write('jkadd %s\n' % ent.sha.encode('hex'))
        count += 1
for i in range(count):
    cli.conn.check_ok()
