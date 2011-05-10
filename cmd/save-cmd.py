#!/usr/bin/env python
import sys, stat, time, math
from bup import hashsplit, git, options, index, client
from bup.helpers import *
from bup.hashsplit import GIT_MODE_TREE, GIT_MODE_FILE, GIT_MODE_SYMLINK


optspec = """
bup save [-tc] [-n name] <filenames...>
--
r,remote=  hostname:/path/to/repo of remote repository
t,tree     output a tree id
c,commit   output a commit id
n,name=    name of backup set to update (if any)
d,date=    date for the commit (seconds since the epoch)
v,verbose  increase log output (can be used more than once)
q,quiet    don't show progress meter
smaller=   only back up files smaller than n bytes
bwlimit=   maximum bytes/sec to transmit to server
f,indexfile=  the name of the index file (normally BUP_DIR/bupindex)
strip      strips the path to every filename given
strip-path= path-prefix to be stripped when saving
graft=     a graft point *old_path*=*new_path* (can be used more than once)
0          set compression-level to 0
9          set compression-level to 9
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()
if not (opt.tree or opt.commit or opt.name):
    o.fatal("use one or more of -t, -c, -n")
if not extra:
    o.fatal("no filenames given")

if opt['0']:
    compression_level = 0
elif opt['9']:
    compression_level = 9
else:
    compression_level = 1

opt.progress = (istty2 and not opt.quiet)
opt.smaller = parse_num(opt.smaller or 0)
if opt.bwlimit:
    client.bwlimit = parse_num(opt.bwlimit)

if opt.date:
    date = parse_date_or_fatal(opt.date, o.fatal)
else:
    date = time.time()

if opt.strip and opt.strip_path:
    o.fatal("--strip is incompatible with --strip-path")

graft_points = []
if opt.graft:
    if opt.strip:
        o.fatal("--strip is incompatible with --graft")

    if opt.strip_path:
        o.fatal("--strip-path is incompatible with --graft")

    for (option, parameter) in flags:
        if option == "--graft":
            splitted_parameter = parameter.split('=')
            if len(splitted_parameter) != 2:
                o.fatal("a graft point must be of the form old_path=new_path")
            graft_points.append((realpath(splitted_parameter[0]),
                                 realpath(splitted_parameter[1])))

is_reverse = os.environ.get('BUP_SERVER_REVERSE')
if is_reverse and opt.remote:
    o.fatal("don't use -r in reverse mode; it's automatic")

if opt.name and opt.name.startswith('.'):
    o.fatal("'%s' is not a valid branch name" % opt.name)
refname = opt.name and 'refs/heads/%s' % opt.name or None
if opt.remote or is_reverse:
    cli = client.Client(opt.remote)
    oldref = refname and cli.read_ref(refname) or None
    w = cli.new_packwriter()
else:
    cli = None
    oldref = refname and git.read_ref(refname) or None
    w = git.PackWriter(compression_level=compression_level)

handle_ctrl_c()


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

def _pop(force_tree):
    assert(len(parts) >= 1)
    part = parts.pop()
    shalist = shalists.pop()
    tree = force_tree or w.new_tree(shalist)
    if shalists:
        shalists[-1].append((GIT_MODE_TREE,
                             git.mangle_name(part,
                                             GIT_MODE_TREE, GIT_MODE_TREE),
                             tree))
    else:  # this was the toplevel, so put it back for sanity
        shalists.append(shalist)
    return tree

lastremain = None
def progress_report(n):
    global count, subcount, lastremain
    subcount += n
    cc = count + subcount
    pct = total and (cc*100.0/total) or 0
    now = time.time()
    elapsed = now - tstart
    kps = elapsed and int(cc/1024./elapsed)
    kps_frac = 10 ** int(math.log(kps+1, 10) - 1)
    kps = int(kps/kps_frac)*kps_frac
    if cc:
        remain = elapsed*1.0/cc * (total-cc)
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
    qprogress('Saving: %.2f%% (%d/%dk, %d/%d files) %s %s\r'
              % (pct, cc/1024, total/1024, fcount, ftotal,
                 remainstr, kpsstr))


indexfile = opt.indexfile or git.repo('bupindex')
r = index.Reader(indexfile)

def already_saved(ent):
    return ent.is_valid() and w.exists(ent.sha) and ent.sha

def wantrecurse_pre(ent):
    return not already_saved(ent)

def wantrecurse_during(ent):
    return not already_saved(ent) or ent.sha_missing()

total = ftotal = 0
if opt.progress:
    for (transname,ent) in r.filter(extra, wantrecurse=wantrecurse_pre):
        if not (ftotal % 10024):
            qprogress('Reading index: %d\r' % ftotal)
        exists = ent.exists()
        hashvalid = already_saved(ent)
        ent.set_sha_missing(not hashvalid)
        if not opt.smaller or ent.size < opt.smaller:
            if exists and not hashvalid:
                total += ent.size
        ftotal += 1
    progress('Reading index: %d, done.\n' % ftotal)
    hashsplit.progress_callback = progress_report

tstart = time.time()
count = subcount = fcount = 0
lastskip_name = None
lastdir = ''
for (transname,ent) in r.filter(extra, wantrecurse=wantrecurse_during):
    (dir, file) = os.path.split(ent.name)
    exists = (ent.flags & index.IX_EXISTS)
    hashvalid = already_saved(ent)
    wasmissing = ent.sha_missing()
    oldsize = ent.size
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
        if opt.verbose >= 2:
            log('%s %-70s\n' % (status, ent.name))
        elif not stat.S_ISDIR(ent.mode) and lastdir != dir:
            if not lastdir.startswith(dir):
                log('%s %-70s\n' % (status, os.path.join(dir, '')))
            lastdir = dir

    if opt.progress:
        progress_report(0)
    fcount += 1
    
    if not exists:
        continue
    if opt.smaller and ent.size >= opt.smaller:
        if exists and not hashvalid:
            add_error('skipping large file "%s"' % ent.name)
            lastskip_name = ent.name
        continue

    assert(dir.startswith('/'))
    if opt.strip:
        stripped_base_path = strip_base_path(dir, extra)
        dirp = stripped_base_path.split('/')
    elif opt.strip_path:
        dirp = strip_path(opt.strip_path, dir).split('/')
    elif graft_points:
        grafted = graft_path(graft_points, dir)
        dirp = grafted.split('/')
    else:
        dirp = dir.split('/')
    while parts > dirp:
        _pop(force_tree = None)
    if dir != '/':
        for part in dirp[len(parts):]:
            _push(part)

    if not file:
        # no filename portion means this is a subdir.  But
        # sub/parentdirectories already handled in the pop/push() part above.
        oldtree = already_saved(ent) # may be None
        newtree = _pop(force_tree = oldtree)
        if not oldtree:
            if lastskip_name and lastskip_name.startswith(ent.name):
                ent.invalidate()
            else:
                ent.validate(GIT_MODE_TREE, newtree)
            ent.repack()
        if exists and wasmissing:
            count += oldsize
        continue

    # it's not a directory
    id = None
    if hashvalid:
        id = ent.sha
        shalists[-1].append((ent.gitmode, 
                             git.mangle_name(file, ent.mode, ent.gitmode),
                             id))
    else:
        if stat.S_ISREG(ent.mode):
            try:
                f = hashsplit.open_noatime(ent.name)
            except (IOError, OSError), e:
                add_error(e)
                lastskip_name = ent.name
            else:
                try:
                    (mode, id) = hashsplit.split_to_blob_or_tree(
                                            w.new_blob, w.new_tree, [f],
                                            keep_boundaries=False)
                except (IOError, OSError), e:
                    add_error('%s: %s' % (ent.name, e))
                    lastskip_name = ent.name
        else:
            if stat.S_ISDIR(ent.mode):
                assert(0)  # handled above
            elif stat.S_ISLNK(ent.mode):
                try:
                    rl = os.readlink(ent.name)
                except (OSError, IOError), e:
                    add_error(e)
                    lastskip_name = ent.name
                else:
                    (mode, id) = (GIT_MODE_SYMLINK, w.new_blob(rl))
            else:
                add_error(Exception('skipping special file "%s"' % ent.name))
                lastskip_name = ent.name
        if id:
            ent.validate(mode, id)
            ent.repack()
            shalists[-1].append((mode,
                                 git.mangle_name(file, ent.mode, ent.gitmode),
                                 id))
    if exists and wasmissing:
        count += oldsize
        subcount = 0


if opt.progress:
    pct = total and count*100.0/total or 100
    progress('Saving: %.2f%% (%d/%dk, %d/%d files), done.    \n'
             % (pct, count/1024, total/1024, fcount, ftotal))

while len(parts) > 1:
    _pop(force_tree = None)
assert(len(shalists) == 1)
tree = w.new_tree(shalists[-1])
if opt.tree:
    print tree.encode('hex')
if opt.commit or opt.name:
    msg = 'bup save\n\nGenerated by command:\n%r' % sys.argv
    commit = w.new_commit(oldref, tree, date, msg)
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
    sys.exit(1)
