#!/usr/bin/env python

import sys
import time

from bup import client, git, options, vfs
from bup.git import get_commit_items
from bup.helpers import add_error, handle_ctrl_c, log, saved_errors

optspec = """
bup rm <branch|save...>
--
#,compress=  set compression level to # (0-9, 9 is highest) [6]
v,verbose    increase verbosity (can be specified multiple times)
unsafe       use the command even though it may be DANGEROUS
"""

def append_commit(hash, parent, cp, writer):
    # Different from bup get's version, which changes the committer.
    # Also removed vestigial author_time assignment, and didn't need
    # opt, name, or get_random_item() call...
    items = get_commit_items(hash, cp)
    tree = items.tree.decode('hex')
    author = '%s <%s>' % (items.author_name, items.author_mail)
    committer = '%s <%s>' % (items.committer_name, items.committer_mail)
    c = writer.new_commit(tree, parent,
                          author, items.author_sec, items.author_offset,
                          committer, items.committer_sec, items.committer_offset,
                          items.message)
    return (c, tree)


def filter_branch(tip_commit_hex, exclude, writer):
    # May return None if everything is excluded.
    commits = [c for _, c in git.rev_list(tip_commit_hex)]
    commits.reverse()
    last_c, tree = None, None
    # Rather than assert that we always find an exclusion here, we'll
    # just let the StopIteration signal the error.
    first_exclusion = next(i for i, c in enumerate(commits) if exclude(c))
    if first_exclusion != 0:
        last_c = commits[first_exclusion - 1]
        tree = get_commit_items(last_c.encode('hex'), git.cp()).tree.decode('hex')
        commits = commits[first_exclusion:]
    for c in commits:
        if exclude(c):
            continue
        last_c, tree = append_commit(c.encode('hex'), last_c, git.cp(), writer)
    return last_c


def rm_saves(saves, writer):
    assert(saves)
    branch_node = saves[0].parent
    for save in saves: # Be certain they're all on the same branch
        assert(save.parent == branch_node)
    rm_commits = frozenset([x.dereference().hash for x in saves])
    orig_tip = branch_node.hash
    new_tip = filter_branch(orig_tip.encode('hex'),
                            lambda x: x in rm_commits,
                            writer)
    assert(orig_tip)
    assert(new_tip != orig_tip)
    return (orig_tip, new_tip)


handle_ctrl_c()

o = options.Options(optspec)
opt, flags, extra = o.parse(sys.argv[1:])

if not opt.unsafe:
    o.fatal('refusing to run dangerous, experimental command without --unsafe')

if len(extra) < 1:
    o.fatal('no paths specified')

paths = extra

git.check_repo_or_die()
top = vfs.RefList(None)

dead_branches = {}
dead_saves = {}

# Scan for bad requests, and opportunities to optimize.
for path in paths:
    try:
        n = top.lresolve(path)
    except vfs.NodeError, e:
        o.fatal(e)
    if isinstance(n, vfs.BranchList): # rm /foo
        branchname = n.name
        dead_branches[branchname] = n
        dead_saves.pop(branchname, None) # rm /foo obviates rm /foo/bar
    elif isinstance(n, vfs.FakeSymlink) and isinstance(n.parent, vfs.BranchList):
        if n.name == 'latest':
            log("error: cannot delete 'latest' symlink")
            sys.exit(1)
        else:
            branchname = n.parent.name
            if branchname not in dead_branches:
                dead_saves.setdefault(branchname, []).append(n)
    else:
        log("error: don't know how to remove %r yet" % n.fullname())
        sys.exit(1)

updated_refs = {}  # ref_name -> (original_ref, tip_commit(bin))
writer = None

if dead_saves:
    writer = git.PackWriter(compression_level=opt.compress)

for branch, saves in dead_saves.iteritems():
    assert(saves)
    updated_refs['refs/heads/' + branch] = rm_saves(saves, writer)
    
for branch, node in dead_branches.iteritems():
    ref = 'refs/heads/' + branch
    assert(not ref in updated_refs)
    updated_refs[ref] = (node.hash, None)

if writer:
    # Must close before we can update the ref(s) below.
    writer.close()

# Only update the refs here, at the very end, so that if something
# goes wrong above, the old refs will be undisturbed.  Make an attempt
# to update each ref.
for ref_name, info in updated_refs.iteritems():
    orig_ref, new_ref = info
    try:
        if not new_ref:
            git.delete_ref(ref_name, orig_ref.encode('hex'))
        else:
            git.update_ref(ref_name, new_ref, orig_ref)
            if opt.verbose:
                new_hex = new_ref.encode('hex')
                if orig_ref:
                    orig_hex = orig_ref.encode('hex')
                    log('updated %r (%s -> %s)\n' % (ref_name, orig_hex, new_hex))
                else:
                    log('updated %r (%s)\n' % (ref_name, new_hex))
    except (git.GitError, client.ClientError), ex:
        if new_ref:
            add_error('while trying to update %r (%s -> %s): %s'
                      % (ref_name, orig_ref, new_ref, ex))
        else:
            add_error('while trying to delete %r (%s): %s'
                      % (ref_name, orig_ref, ex))

if saved_errors:
    log('warning: %d errors encountered\n' % len(saved_errors))
    sys.exit(1)
