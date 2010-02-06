#!/usr/bin/env python
import sys, re, errno, stat, time, math
import hashsplit, git, options, index, client
from helpers import *


optspec = """
bup save [-tc] [-n name] <filenames...>
--
r,remote=  remote repository path
t,tree     output a tree id
c,commit   output a commit id
n,name=    name of backup set to update (if any)
v,verbose  increase log output (can be used more than once)
q,quiet    don't show progress meter
smaller=   only back up files smaller than n bytes
"""
o = options.Options('bup save', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()
if not (opt.tree or opt.commit or opt.name):
    log("bup save: use one or more of -t, -c, -n\n")
    o.usage()
if not extra:
    log("bup save: no filenames given.\n")
    o.usage()

opt.progress = (istty and not opt.quiet)

refname = opt.name and 'refs/heads/%s' % opt.name or None
if opt.remote:
    cli = client.Client(opt.remote)
    oldref = refname and cli.read_ref(refname) or None
    w = cli.new_packwriter()
else:
    cli = None
    oldref = refname and git.read_ref(refname) or None
    w = git.PackWriter()


def eatslash(dir):
    if dir.endswith('/'):
        return dir[:-1]
    else:
        return dir


parts = ['']
shalists = [[]]

def _push(part):
    assert(part)
    parts.append(part)
    shalists.append([])

def _pop():
    assert(len(parts) > 1)
    part = parts.pop()
    shalist = shalists.pop()
    tree = w.new_tree(shalist)
    shalists[-1].append(('40000', part, tree))

lastremain = None
def progress_report(n):
    global count, lastremain
    count += n
    pct = total and (count*100.0/total) or 0
    now = time.time()
    elapsed = now - tstart
    kps = elapsed and int(count/1024./elapsed)
    kps_frac = 10 ** int(math.log(kps+1, 10) - 1)
    kps = int(kps/kps_frac)*kps_frac
    if count:
        remain = elapsed*1.0/count * (total-count)
    else:
        remain = 0.0
    if (lastremain and (remain > lastremain)
          and ((remain - lastremain)/lastremain < 0.05)):
        remain = lastremain
    else:
        lastremain = remain
    hours = int(remain/60/60)
    mins = int(remain/60 - hours*60)
    secs = int(remain - hours*60*60 - mins*60)
    if elapsed < 30:
        remainstr = ''
        kpsstr = ''
    else:
        kpsstr = '%dk/s' % kps
        if hours:
            remainstr = '%dh%dm' % (hours, mins)
        elif mins:
            remainstr = '%dm%d' % (mins, secs)
        else:
            remainstr = '%ds' % secs
    progress('Saving: %.2f%% (%d/%dk, %d/%d files) %s %s     \r'
             % (pct, count/1024, total/1024, fcount, ftotal,
                remainstr, kpsstr))


r = index.Reader(git.repo('bupindex'))

total = ftotal = 0
if opt.progress:
    for (transname,ent) in r.filter(extra):
        if not (ftotal % 10024):
            progress('Reading index: %d\r' % ftotal)
        exists = (ent.flags & index.IX_EXISTS)
        hashvalid = (ent.flags & index.IX_HASHVALID) and w.exists(ent.sha)
        if exists and not hashvalid:
            total += ent.size
        ftotal += 1
    progress('Reading index: %d, done.\n' % ftotal)
    hashsplit.progress_callback = progress_report

tstart = time.time()
count = fcount = 0
for (transname,ent) in r.filter(extra):
    (dir, file) = os.path.split(ent.name)
    exists = (ent.flags & index.IX_EXISTS)
    hashvalid = (ent.flags & index.IX_HASHVALID) and w.exists(ent.sha)
    if opt.verbose:
        if not exists:
            status = 'D'
        elif not hashvalid:
            if ent.sha == index.EMPTY_SHA:
                status = 'A'
            else:
                status = 'M'
        else:
            status = ' '
        if opt.verbose >= 2 or stat.S_ISDIR(ent.mode):
            log('%s %-70s\n' % (status, ent.name))

    if opt.progress:
        progress_report(0)
    fcount += 1
    
    if not exists:
        continue

    assert(dir.startswith('/'))
    dirp = dir.split('/')
    while parts > dirp:
        _pop()
    if dir != '/':
        for part in dirp[len(parts):]:
            _push(part)

    if not file:
        # directory already handled.
        # FIXME: not using the indexed tree sha1's for anything, which is
        # a waste.  That's a potential optimization...
        count += ent.size
        continue  

    id = None
    if hashvalid:
        mode = '%o' % ent.mode
        id = ent.sha
        shalists[-1].append((mode, file, id))
    elif opt.smaller and ent.size >= opt.smaller:
        add_error('skipping large file "%s"' % ent.name)
    else:
        if stat.S_ISREG(ent.mode):
            try:
                f = open(ent.name)
            except IOError, e:
                add_error(e)
            except OSError, e:
                add_error(e)
            else:
                (mode, id) = hashsplit.split_to_blob_or_tree(w, [f])
        else:
            if stat.S_ISDIR(ent.mode):
                assert(0)  # handled above
            elif stat.S_ISLNK(ent.mode):
                try:
                    rl = os.readlink(ent.name)
                except OSError, e:
                    add_error(e)
                except IOError, e:
                    add_error(e)
                else:
                    (mode, id) = ('120000', w.new_blob(rl))
            else:
                add_error(Exception('skipping special file "%s"' % ent.name))
            count += ent.size
        if id:
            ent.validate(id)
            ent.repack()
            shalists[-1].append((mode, file, id))

if opt.progress:
    pct = total and count*100.0/total or 100
    progress('Saving: %.2f%% (%d/%dk, %d/%d files), done.    \n'
             % (pct, count/1024, total/1024, fcount, ftotal))

#log('parts out: %r\n' % parts)
#log('stk out: %r\n' % shalists)
while len(parts) > 1:
    _pop()
#log('parts out: %r\n' % parts)
#log('stk out: %r\n' % shalists)
assert(len(shalists) == 1)
tree = w.new_tree(shalists[-1])
if opt.tree:
    print tree.encode('hex')
if opt.commit or opt.name:
    msg = 'bup save\n\nGenerated by command:\n%r' % sys.argv
    ref = opt.name and ('refs/heads/%s' % opt.name) or None
    commit = w.new_commit(oldref, tree, msg)
    if opt.commit:
        print commit.encode('hex')

w.close()  # must close before we can update the ref
        
if opt.name:
    if cli:
        cli.update_ref(refname, commit, oldref)
    else:
        git.update_ref(refname, commit, oldref)

if cli:
    cli.close()

if saved_errors:
    log('WARNING: %d errors encountered while saving.\n' % len(saved_errors))
