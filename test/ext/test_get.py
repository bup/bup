
from __future__ import print_function
from errno import ENOENT
from itertools import product
from os import chdir, mkdir, rename
from shutil import rmtree
from subprocess import PIPE
import pytest, re, sys

from bup import compat, path
from bup.compat import environ, getcwd, items
from bup.helpers import bquote, merge_dict, unlink
from bup.io import byte_stream
from buptest import ex, exo
from wvpytest import wvcheck, wvfail, wvmsg, wvpass, wvpasseq, wvpassne, wvstart
import bup.path


sys.stdout.flush()
stdout = byte_stream(sys.stdout)

# FIXME: per-test function
environ[b'GIT_AUTHOR_NAME'] = b'bup test-get'
environ[b'GIT_COMMITTER_NAME'] = b'bup test-get'
environ[b'GIT_AUTHOR_EMAIL'] = b'bup@85430dcca2b611e4b2c3-8f5691723476'
environ[b'GIT_COMMITTER_EMAIL'] = b'bup@85430dcca2b611e4b2c3-8f5691723476'

# The clean-repo test can probably be applied more broadly.  It was
# initially just applied to test-pick to catch a bug.

top = getcwd()
bup_cmd = bup.path.exe()

def rmrf(path):
    err = []  # because python's scoping mess...
    def onerror(function, path, excinfo):
        err.append((function, path, excinfo))
    rmtree(path, onerror=onerror)
    if err:
        function, path, excinfo = err[0]
        ex_type, ex, traceback = excinfo
        if (not isinstance(ex, OSError)) or ex.errno != ENOENT:
            raise ex

def verify_trees_match(path1, path2):
    global top
    exr = exo((top + b'/dev/compare-trees', b'-c', path1, path2), check=False)
    stdout.write(exr.out)
    sys.stdout.flush()
    wvcheck(exr.rc == 0, 'process exit %d == 0' % exr.rc)

def verify_rcz(cmd, **kwargs):
    assert not kwargs.get('check')
    kwargs['check'] = False
    result = exo(cmd, **kwargs)
    stdout.write(result.out)
    rc = result.proc.returncode
    wvcheck(rc == 0, 'process exit %d == 0' % rc)
    return result

# FIXME: multline, or allow opts generally?

def verify_rx(rx, string):
    wvcheck(re.search(rx, string), 'rx %r matches %r' % (rx, string))

def verify_nrx(rx, string):
    wvcheck(not re.search(rx, string), "rx %r doesn't match %r" % (rx, string))

def validate_clean_repo():
    out = verify_rcz((b'git', b'--git-dir', b'get-dest', b'fsck')).out
    verify_nrx(br'dangling|mismatch|missing|unreachable', out)
    
def validate_blob(src_id, dest_id):
    global top
    rmrf(b'restore-src')
    rmrf(b'restore-dest')
    cat_tree = top + b'/dev/git-cat-tree'
    src_blob = verify_rcz((cat_tree, b'--git-dir', b'get-src', src_id)).out
    dest_blob = verify_rcz((cat_tree, b'--git-dir', b'get-src', src_id)).out
    wvpasseq(src_blob, dest_blob)

def validate_tree(src_id, dest_id):

    rmrf(b'restore-src')
    rmrf(b'restore-dest')
    mkdir(b'restore-src')
    mkdir(b'restore-dest')
    
    commit_env = merge_dict(environ, {b'GIT_COMMITTER_DATE': b'2014-01-01 01:01'})

    # Create a commit so the archive contents will have matching timestamps.
    src_c = exo((b'git', b'--git-dir', b'get-src',
                 b'commit-tree', b'-m', b'foo', src_id),
                env=commit_env).out.strip()
    dest_c = exo((b'git', b'--git-dir', b'get-dest',
                  b'commit-tree', b'-m', b'foo', dest_id),
                 env=commit_env).out.strip()
    exr = verify_rcz(b'git --git-dir get-src archive %s | tar xvf - -C restore-src'
                     % bquote(src_c),
                     shell=True)
    if exr.rc != 0: return False
    exr = verify_rcz(b'git --git-dir get-dest archive %s | tar xvf - -C restore-dest'
                     % bquote(dest_c),
                     shell=True)
    if exr.rc != 0: return False
    
    # git archive doesn't include an entry for ./.
    unlink(b'restore-src/pax_global_header')
    unlink(b'restore-dest/pax_global_header')
    ex((b'touch', b'-r', b'restore-src', b'restore-dest'))
    verify_trees_match(b'restore-src/', b'restore-dest/')
    rmrf(b'restore-src')
    rmrf(b'restore-dest')

def validate_commit(src_id, dest_id):
    exr = verify_rcz((b'git', b'--git-dir', b'get-src', b'cat-file', b'commit', src_id))
    if exr.rc != 0: return False
    src_cat = exr.out
    exr = verify_rcz((b'git', b'--git-dir', b'get-dest', b'cat-file', b'commit', dest_id))
    if exr.rc != 0: return False
    dest_cat = exr.out
    wvpasseq(src_cat, dest_cat)
    if src_cat != dest_cat: return False
    
    rmrf(b'restore-src')
    rmrf(b'restore-dest')
    mkdir(b'restore-src')
    mkdir(b'restore-dest')
    qsrc = bquote(src_id)
    qdest = bquote(dest_id)
    exr = verify_rcz((b'git --git-dir get-src archive ' + qsrc
                      + b' | tar xf - -C restore-src'),
                     shell=True)
    if exr.rc != 0: return False
    exr = verify_rcz((b'git --git-dir get-dest archive ' + qdest +
                      b' | tar xf - -C restore-dest'),
                     shell=True)
    if exr.rc != 0: return False
    
    # git archive doesn't include an entry for ./.
    ex((b'touch', b'-r', b'restore-src', b'restore-dest'))
    verify_trees_match(b'restore-src/', b'restore-dest/')
    rmrf(b'restore-src')
    rmrf(b'restore-dest')

def _validate_save(orig_dir, save_path, commit_id, tree_id):
    global bup_cmd
    rmrf(b'restore')
    exr = verify_rcz((bup_cmd, b'-d', b'get-dest',
                      b'restore', b'-C', b'restore', save_path + b'/.'))
    if exr.rc: return False
    verify_trees_match(orig_dir + b'/', b'restore/')
    if tree_id:
        # FIXME: double check that get-dest is correct
        exr = verify_rcz((b'git', b'--git-dir', b'get-dest', b'ls-tree', tree_id))
        if exr.rc: return False
        cat = verify_rcz((b'git', b'--git-dir', b'get-dest',
                          b'cat-file', b'commit', commit_id))
        if cat.rc: return False
        wvpasseq(b'tree ' + tree_id, cat.out.splitlines()[0])

# FIXME: re-merge save and new_save?
        
def validate_save(dest_name, restore_subpath, commit_id, tree_id, orig_value,
                  get_out):
    out = get_out.splitlines()
    print('blarg: out', repr(out), file=sys.stderr)
    wvpasseq(2, len(out))
    get_tree_id = out[0]
    get_commit_id = out[1]
    wvpasseq(tree_id, get_tree_id)
    wvpasseq(commit_id, get_commit_id)
    _validate_save(orig_value, dest_name + restore_subpath, commit_id, tree_id)

def validate_new_save(dest_name, restore_subpath, commit_id, tree_id, orig_value,
                      get_out):
    out = get_out.splitlines()
    wvpasseq(2, len(out))
    get_tree_id = out[0]
    get_commit_id = out[1]
    wvpasseq(tree_id, get_tree_id)
    wvpassne(commit_id, get_commit_id)
    _validate_save(orig_value, dest_name + restore_subpath, get_commit_id, tree_id)
        
def validate_tagged_save(tag_name, restore_subpath,
                         commit_id, tree_id, orig_value, get_out):
    out = get_out.splitlines()
    wvpasseq(1, len(out))
    get_tag_id = out[0]
    wvpasseq(commit_id, get_tag_id)
    # Make sure tmp doesn't already exist.
    exr = exo((b'git', b'--git-dir', b'get-dest', b'show-ref', b'tmp-branch-for-tag'),
              check=False)
    wvpasseq(1, exr.rc)

    ex((b'git', b'--git-dir', b'get-dest', b'branch', b'tmp-branch-for-tag',
        b'refs/tags/' + tag_name))
    _validate_save(orig_value, b'tmp-branch-for-tag/latest' + restore_subpath,
                   commit_id, tree_id)
    ex((b'git', b'--git-dir', b'get-dest', b'branch', b'-D', b'tmp-branch-for-tag'))

def validate_new_tagged_commit(tag_name, commit_id, tree_id, get_out):
    out = get_out.splitlines()
    wvpasseq(1, len(out))
    get_tag_id = out[0]
    wvpassne(commit_id, get_tag_id)
    validate_tree(tree_id, tag_name + b':')


def _run_get(disposition, method, what):
    print('run_get:', repr((disposition, method, what)), file=sys.stderr)
    global bup_cmd

    if disposition == 'get':
        get_cmd = (bup_cmd, b'-d', b'get-dest',
                   b'get', b'-vvct', b'--print-tags', b'-s', b'get-src')
    elif disposition == 'get-on':
        get_cmd = (bup_cmd, b'-d', b'get-dest',
                   b'on', b'-', b'get', b'-vvct', b'--print-tags', b'-s', b'get-src')
    elif disposition == 'get-to':
        get_cmd = (bup_cmd, b'-d', b'get-dest',
                   b'get', b'-vvct', b'--print-tags', b'-s', b'get-src',
                   b'-r', b'-:' + getcwd() + b'/get-dest')
    else:
        raise Exception('error: unexpected get disposition ' + repr(disposition))
    
    if isinstance(what, bytes):
        cmd = get_cmd + (method, what)
    else:
        assert not isinstance(what, str)  # python 3 sanity check
        if method in (b'--ff', b'--append', b'--pick', b'--force-pick', b'--new-tag',
                      b'--replace'):
            method += b':'
        src, dest = what
        cmd = get_cmd + (method, src, dest)
    result = exo(cmd, check=False, stderr=PIPE)
    fsck = ex((bup_cmd, b'-d', b'get-dest', b'fsck'), check=False)
    wvpasseq(0, fsck.rc)
    return result

def run_get(disposition, method, what=None, given=None):
    global bup_cmd
    rmrf(b'get-dest')
    ex((bup_cmd, b'-d', b'get-dest', b'init'))

    if given:
        # FIXME: replace bup-get with independent commands as is feasible
        exr = _run_get(disposition, b'--replace', given)
        assert not exr.rc
    return _run_get(disposition, method, what)

def _test_universal(get_disposition, src_info):
    methods = (b'--ff', b'--append', b'--pick', b'--force-pick', b'--new-tag',
               b'--replace', b'--unnamed')
    for method in methods:
        mmsg = method.decode('ascii')
        wvstart(get_disposition + ' ' + mmsg + ', missing source, fails')
        exr = run_get(get_disposition, method, b'not-there')
        wvpassne(0, exr.rc)
        verify_rx(br'cannot find source', exr.err)
    for method in methods:
        mmsg = method.decode('ascii')
        wvstart(get_disposition + ' ' + mmsg + ' / fails')
        exr = run_get(get_disposition, method, b'/')
        wvpassne(0, exr.rc)
        verify_rx(b'cannot fetch entire repository', exr.err)

def verify_only_refs(**kwargs):
    for kind, refs in items(kwargs):
        if kind == 'heads':
            abs_refs = [b'refs/heads/' + ref for ref in refs]
            karg = b'--heads'
        elif kind == 'tags':
            abs_refs = [b'refs/tags/' + ref for ref in refs]
            karg = b'--tags'
        else:
            raise TypeError('unexpected keyword argument %r' % kind)
        if abs_refs:
            verify_rcz([b'git', b'--git-dir', b'get-dest',
                        b'show-ref', b'--verify', karg] + abs_refs)
            exr = exo((b'git', b'--git-dir', b'get-dest', b'show-ref', karg),
                      check=False)
            wvpasseq(0, exr.rc)
            expected_refs = sorted(abs_refs)
            repo_refs = sorted([x.split()[1] for x in exr.out.splitlines()])
            wvpasseq(expected_refs, repo_refs)
        else:
            # FIXME: can we just check "git show-ref --heads == ''"?
            exr = exo((b'git', b'--git-dir', b'get-dest', b'show-ref', karg),
                      check=False)
            wvpasseq(1, exr.rc)
            wvpasseq(b'', exr.out.strip())

def _test_replace(get_disposition, src_info):
    print('blarg:', repr(src_info), file=sys.stderr)

    wvstart(get_disposition + ' --replace to root fails')
    for item in (b'.tag/tinyfile',
                 b'src/latest' + src_info['tinyfile-path'],
                 b'.tag/subtree',
                 b'src/latest' + src_info['subtree-vfs-path'],
                 b'.tag/commit-1',
                 b'src/latest',
                 b'src'):
        exr = run_get(get_disposition, b'--replace', (item, b'/'))
        wvpassne(0, exr.rc)
        verify_rx(br'impossible; can only overwrite branch or tag', exr.err)

    tinyfile_id = src_info['tinyfile-id']
    tinyfile_path = src_info['tinyfile-path']
    subtree_vfs_path = src_info['subtree-vfs-path']
    subtree_id = src_info['subtree-id']
    commit_2_id = src_info['commit-2-id']
    tree_2_id = src_info['tree-2-id']

    # Anything to tag
    existing_items = {'nothing' : None,
                      'blob' : (b'.tag/tinyfile', b'.tag/obj'),
                      'tree' : (b'.tag/tree-1', b'.tag/obj'),
                      'commit': (b'.tag/commit-1', b'.tag/obj')}
    for ex_type, ex_ref in items(existing_items):
        wvstart(get_disposition + ' --replace ' + ex_type + ' with blob tag')
        for item in (b'.tag/tinyfile', b'src/latest' + tinyfile_path):
            exr = run_get(get_disposition, b'--replace', (item ,b'.tag/obj'),
                          given=ex_ref)
            wvpasseq(0, exr.rc)        
            validate_blob(tinyfile_id, tinyfile_id)
            verify_only_refs(heads=[], tags=(b'obj',))
        wvstart(get_disposition + ' --replace ' + ex_type + ' with tree tag')
        for item in (b'.tag/subtree',  b'src/latest' + subtree_vfs_path):
            exr = run_get(get_disposition, b'--replace', (item, b'.tag/obj'),
                          given=ex_ref)
            validate_tree(subtree_id, subtree_id)
            verify_only_refs(heads=[], tags=(b'obj',))
        wvstart(get_disposition + ' --replace ' + ex_type + ' with commitish tag')
        for item in (b'.tag/commit-2', b'src/latest', b'src'):
            exr = run_get(get_disposition, b'--replace', (item, b'.tag/obj'),
                          given=ex_ref)
            validate_tagged_save(b'obj', getcwd() + b'/src',
                                 commit_2_id, tree_2_id, b'src-2', exr.out)
            verify_only_refs(heads=[], tags=(b'obj',))

        # Committish to branch.
        existing_items = (('nothing', None),
                          ('branch', (b'.tag/commit-1', b'obj')))
        for ex_type, ex_ref in existing_items:
            for item_type, item in (('commit', b'.tag/commit-2'),
                                    ('save', b'src/latest'),
                                    ('branch', b'src')):
                wvstart(get_disposition + ' --replace '
                        + ex_type + ' with ' + item_type)
                exr = run_get(get_disposition, b'--replace', (item, b'obj'),
                              given=ex_ref)
                validate_save(b'obj/latest', getcwd() + b'/src',
                              commit_2_id, tree_2_id, b'src-2', exr.out)
                verify_only_refs(heads=(b'obj',), tags=[])

        # Not committish to branch
        existing_items = (('nothing', None),
                          ('branch', (b'.tag/commit-1', b'obj')))
        for ex_type, ex_ref in existing_items:
            for item_type, item in (('blob', b'.tag/tinyfile'),
                                    ('blob', b'src/latest' + tinyfile_path),
                                    ('tree', b'.tag/subtree'),
                                    ('tree', b'src/latest' + subtree_vfs_path)):
                wvstart(get_disposition + ' --replace branch with '
                        + item_type + ' given ' + ex_type + ' fails')

                exr = run_get(get_disposition, b'--replace', (item, b'obj'),
                              given=ex_ref)
                wvpassne(0, exr.rc)
                verify_rx(br'cannot overwrite branch with .+ for', exr.err)

        wvstart(get_disposition + ' --replace, implicit destinations')

        exr = run_get(get_disposition, b'--replace', b'src')
        validate_save(b'src/latest', getcwd() + b'/src',
                      commit_2_id, tree_2_id, b'src-2', exr.out)
        verify_only_refs(heads=(b'src',), tags=[])

        exr = run_get(get_disposition, b'--replace', b'.tag/commit-2')
        validate_tagged_save(b'commit-2', getcwd() + b'/src',
                             commit_2_id, tree_2_id, b'src-2', exr.out)
        verify_only_refs(heads=[], tags=(b'commit-2',))

def _test_ff(get_disposition, src_info):

    wvstart(get_disposition + ' --ff to root fails')
    tinyfile_path = src_info['tinyfile-path']
    for item in (b'.tag/tinyfile', b'src/latest' + tinyfile_path):
        exr = run_get(get_disposition, b'--ff', (item, b'/'))
        wvpassne(0, exr.rc)
        verify_rx(br'source for .+ must be a branch, save, or commit', exr.err)
    subtree_vfs_path = src_info['subtree-vfs-path']
    for item in (b'.tag/subtree', b'src/latest' + subtree_vfs_path):
        exr = run_get(get_disposition, b'--ff', (item, b'/'))
        wvpassne(0, exr.rc)
        verify_rx(br'is impossible; can only --append a tree to a branch',
                  exr.err)    
    for item in (b'.tag/commit-1', b'src/latest', b'src'):
        exr = run_get(get_disposition, b'--ff', (item, b'/'))
        wvpassne(0, exr.rc)
        verify_rx(br'destination for .+ is a root, not a branch', exr.err)

    wvstart(get_disposition + ' --ff of not-committish fails')
    for src in (b'.tag/tinyfile', b'src/latest' + tinyfile_path):
        # FIXME: use get_item elsewhere?
        for given, get_item in ((None, (src, b'obj')),
                                (None, (src, b'.tag/obj')),
                                ((b'.tag/tinyfile', b'.tag/obj'), (src, b'.tag/obj')),
                                ((b'.tag/tree-1', b'.tag/obj'), (src, b'.tag/obj')),
                                ((b'.tag/commit-1', b'.tag/obj'), (src, b'.tag/obj')),
                                ((b'.tag/commit-1', b'obj'), (src, b'obj'))):
            exr = run_get(get_disposition, b'--ff', get_item, given=given)
            wvpassne(0, exr.rc)
            verify_rx(br'must be a branch, save, or commit', exr.err)
    for src in (b'.tag/subtree', b'src/latest' + subtree_vfs_path):
        for given, get_item in ((None, (src, b'obj')),
                                (None, (src, b'.tag/obj')),
                                ((b'.tag/tinyfile', b'.tag/obj'), (src, b'.tag/obj')),
                                ((b'.tag/tree-1', b'.tag/obj'), (src, b'.tag/obj')),
                                ((b'.tag/commit-1', b'.tag/obj'), (src, b'.tag/obj')),
                                ((b'.tag/commit-1', b'obj'), (src, b'obj'))):
            exr = run_get(get_disposition, b'--ff', get_item, given=given)
            wvpassne(0, exr.rc)
            verify_rx(br'can only --append a tree to a branch', exr.err)

    wvstart(get_disposition + ' --ff committish, ff possible')
    save_2 = src_info['save-2']
    for src in (b'.tag/commit-2', b'src/' + save_2, b'src'):
        for given, get_item, complaint in \
            ((None, (src, b'.tag/obj'),
              br'destination .+ must be a valid branch name'),
             ((b'.tag/tinyfile', b'.tag/obj'), (src, b'.tag/obj'),
              br'destination .+ is a blob, not a branch'),
             ((b'.tag/tree-1', b'.tag/obj'), (src, b'.tag/obj'),
              br'destination .+ is a tree, not a branch'),
             ((b'.tag/commit-1', b'.tag/obj'), (src, b'.tag/obj'),
              br'destination .+ is a tagged commit, not a branch'),
             ((b'.tag/commit-2', b'.tag/obj'), (src, b'.tag/obj'),
              br'destination .+ is a tagged commit, not a branch')):
            exr = run_get(get_disposition, b'--ff', get_item, given=given)
            wvpassne(0, exr.rc)
            verify_rx(complaint, exr.err)
    # FIXME: use src or item and given or existing consistently in loops...
    commit_2_id = src_info['commit-2-id']
    tree_2_id = src_info['tree-2-id']
    for src in (b'.tag/commit-2', b'src/' + save_2, b'src'):
        for given in (None, (b'.tag/commit-1', b'obj'), (b'.tag/commit-2', b'obj')):
            exr = run_get(get_disposition, b'--ff', (src, b'obj'), given=given)
            wvpasseq(0, exr.rc)
            validate_save(b'obj/latest', getcwd() + b'/src',
                          commit_2_id, tree_2_id, b'src-2', exr.out)
            verify_only_refs(heads=(b'obj',), tags=[])
            
    wvstart(get_disposition + ' --ff, implicit destinations')
    for item in (b'src', b'src/latest'):
        exr = run_get(get_disposition, b'--ff', item)
        wvpasseq(0, exr.rc)

        ex((b'find', b'get-dest/refs'))
        ex((bup_cmd, b'-d', b'get-dest', b'ls'))

        validate_save(b'src/latest', getcwd() + b'/src',
                     commit_2_id, tree_2_id, b'src-2', exr.out)
        #verify_only_refs(heads=('src',), tags=[])

    wvstart(get_disposition + ' --ff, ff impossible')
    for given, get_item in (((b'unrelated-branch', b'src'), b'src'),
                            ((b'.tag/commit-2', b'src'), (b'.tag/commit-1', b'src'))):
        exr = run_get(get_disposition, b'--ff', get_item, given=given)
        wvpassne(0, exr.rc)
        verify_rx(br'destination is not an ancestor of source', exr.err)

def _test_append(get_disposition, src_info):
    tinyfile_path = src_info['tinyfile-path']
    subtree_vfs_path = src_info['subtree-vfs-path']

    wvstart(get_disposition + ' --append to root fails')
    for item in (b'.tag/tinyfile', b'src/latest' + tinyfile_path):
        exr = run_get(get_disposition, b'--append', (item, b'/'))
        wvpassne(0, exr.rc)
        verify_rx(br'source for .+ must be a branch, save, commit, or tree',
                  exr.err)
    for item in (b'.tag/subtree', b'src/latest' + subtree_vfs_path,
                 b'.tag/commit-1', b'src/latest', b'src'):
        exr = run_get(get_disposition, b'--append', (item, b'/'))
        wvpassne(0, exr.rc)
        verify_rx(br'destination for .+ is a root, not a branch', exr.err)

    wvstart(get_disposition + ' --append of not-treeish fails')
    for src in (b'.tag/tinyfile', b'src/latest' + tinyfile_path):
        for given, item in ((None, (src, b'obj')),
                            (None, (src, b'.tag/obj')),
                            ((b'.tag/tinyfile', b'.tag/obj'), (src, b'.tag/obj')),
                            ((b'.tag/tree-1', b'.tag/obj'), (src, b'.tag/obj')),
                            ((b'.tag/commit-1', b'.tag/obj'), (src, b'.tag/obj')),
                            ((b'.tag/commit-1', b'obj'), (src, b'obj'))):
            exr = run_get(get_disposition, b'--append', item, given=given)
            wvpassne(0, exr.rc)
            verify_rx(br'must be a branch, save, commit, or tree', exr.err)

    wvstart(get_disposition + ' --append committish failure cases')
    save_2 = src_info['save-2']
    for src in (b'.tag/subtree', b'src/latest' + subtree_vfs_path,
                b'.tag/commit-2', b'src/' + save_2, b'src'):
        for given, item, complaint in \
            ((None, (src, b'.tag/obj'),
              br'destination .+ must be a valid branch name'),
             ((b'.tag/tinyfile', b'.tag/obj'), (src, b'.tag/obj'),
              br'destination .+ is a blob, not a branch'),
             ((b'.tag/tree-1', b'.tag/obj'), (src, b'.tag/obj'),
              br'destination .+ is a tree, not a branch'),
             ((b'.tag/commit-1', b'.tag/obj'), (src, b'.tag/obj'),
              br'destination .+ is a tagged commit, not a branch'),
             ((b'.tag/commit-2', b'.tag/obj'), (src, b'.tag/obj'),
              br'destination .+ is a tagged commit, not a branch')):
            exr = run_get(get_disposition, b'--append', item, given=given)
            wvpassne(0, exr.rc)
            verify_rx(complaint, exr.err)

    wvstart(get_disposition + ' --append committish')
    commit_2_id = src_info['commit-2-id']
    tree_2_id = src_info['tree-2-id']
    for item in (b'.tag/commit-2', b'src/' + save_2, b'src'):
        for existing in (None, (b'.tag/commit-1', b'obj'),
                         (b'.tag/commit-2', b'obj'),
                         (b'unrelated-branch', b'obj')):
            exr = run_get(get_disposition, b'--append', (item, b'obj'),
                          given=existing)
            wvpasseq(0, exr.rc)
            validate_new_save(b'obj/latest', getcwd() + b'/src',
                              commit_2_id, tree_2_id, b'src-2', exr.out)
            verify_only_refs(heads=(b'obj',), tags=[])
    # Append ancestor
    save_1 = src_info['save-1']
    commit_1_id = src_info['commit-1-id']
    tree_1_id = src_info['tree-1-id']
    for item in (b'.tag/commit-1',  b'src/' + save_1, b'src-1'):
        exr = run_get(get_disposition, b'--append', (item, b'obj'),
                      given=(b'.tag/commit-2', b'obj'))
        wvpasseq(0, exr.rc)
        validate_new_save(b'obj/latest', getcwd() + b'/src',
                          commit_1_id, tree_1_id, b'src-1', exr.out)
        verify_only_refs(heads=(b'obj',), tags=[])

    wvstart(get_disposition + ' --append tree')
    subtree_path = src_info['subtree-path']
    subtree_id = src_info['subtree-id']
    for item in (b'.tag/subtree', b'src/latest' + subtree_vfs_path):
        for existing in (None,
                         (b'.tag/commit-1', b'obj'),
                         (b'.tag/commit-2', b'obj')):
            exr = run_get(get_disposition, b'--append', (item, b'obj'),
                          given=existing)
            wvpasseq(0, exr.rc)
            validate_new_save(b'obj/latest', b'/', None, subtree_id, subtree_path,
                              exr.out)
            verify_only_refs(heads=(b'obj',), tags=[])

    wvstart(get_disposition + ' --append, implicit destinations')

    for item in (b'src', b'src/latest'):
        exr = run_get(get_disposition, b'--append', item)
        wvpasseq(0, exr.rc)
        validate_new_save(b'src/latest', getcwd() + b'/src', commit_2_id, tree_2_id,
                          b'src-2', exr.out)
        verify_only_refs(heads=(b'src',), tags=[])

def _test_pick_common(get_disposition, src_info, force=False):
    flavor = b'--force-pick' if force else b'--pick'
    flavormsg = flavor.decode('ascii')
    tinyfile_path = src_info['tinyfile-path']
    subtree_vfs_path = src_info['subtree-vfs-path']
    
    wvstart(get_disposition + ' ' + flavormsg + ' to root fails')
    for item in (b'.tag/tinyfile', b'src/latest' + tinyfile_path, b'src'):
        exr = run_get(get_disposition, flavor, (item, b'/'))
        wvpassne(0, exr.rc)
        verify_rx(br'can only pick a commit or save', exr.err)
    for item in (b'.tag/commit-1', b'src/latest'):
        exr = run_get(get_disposition, flavor, (item, b'/'))
        wvpassne(0, exr.rc)
        verify_rx(br'destination is not a tag or branch', exr.err)
    for item in (b'.tag/subtree', b'src/latest' + subtree_vfs_path):
        exr = run_get(get_disposition, flavor, (item, b'/'))
        wvpassne(0, exr.rc)
        verify_rx(br'is impossible; can only --append a tree', exr.err)

    wvstart(get_disposition + ' ' + flavormsg + ' of blob or branch fails')
    for item in (b'.tag/tinyfile', b'src/latest' + tinyfile_path, b'src'):
        for given, get_item in ((None, (item, b'obj')),
                                (None, (item, b'.tag/obj')),
                                ((b'.tag/tinyfile', b'.tag/obj'), (item, b'.tag/obj')),
                                ((b'.tag/tree-1', b'.tag/obj'), (item, b'.tag/obj')),
                                ((b'.tag/commit-1', b'.tag/obj'), (item, b'.tag/obj')),
                                ((b'.tag/commit-1', b'obj'), (item, b'obj'))):
            exr = run_get(get_disposition, flavor, get_item, given=given)
            wvpassne(0, exr.rc)
            verify_rx(br'impossible; can only pick a commit or save', exr.err)

    wvstart(get_disposition + ' ' + flavormsg + ' of tree fails')
    for item in (b'.tag/subtree', b'src/latest' + subtree_vfs_path):
        for given, get_item in ((None, (item, b'obj')),
                                (None, (item, b'.tag/obj')),
                                ((b'.tag/tinyfile', b'.tag/obj'), (item, b'.tag/obj')),
                                ((b'.tag/tree-1', b'.tag/obj'), (item, b'.tag/obj')),
                                ((b'.tag/commit-1', b'.tag/obj'), (item, b'.tag/obj')),
                                ((b'.tag/commit-1', b'obj'), (item, b'obj'))):
            exr = run_get(get_disposition, flavor, get_item, given=given)
            wvpassne(0, exr.rc)
            verify_rx(br'impossible; can only --append a tree', exr.err)

    save_2 = src_info['save-2']
    commit_2_id = src_info['commit-2-id']
    tree_2_id = src_info['tree-2-id']
    # FIXME: these two wvstart texts?
    if force:
        wvstart(get_disposition + ' ' + flavormsg + ' commit/save to existing tag')
        for item in (b'.tag/commit-2', b'src/' + save_2):
            for given in ((b'.tag/tinyfile', b'.tag/obj'),
                          (b'.tag/tree-1', b'.tag/obj'),
                          (b'.tag/commit-1', b'.tag/obj')):
                exr = run_get(get_disposition, flavor, (item, b'.tag/obj'),
                              given=given)
                wvpasseq(0, exr.rc)
                validate_new_tagged_commit(b'obj', commit_2_id, tree_2_id,
                                           exr.out)
                verify_only_refs(heads=[], tags=(b'obj',))
    else: # --pick
        wvstart(get_disposition + ' ' + flavormsg
                + ' commit/save to existing tag fails')
        for item in (b'.tag/commit-2', b'src/' + save_2):
            for given in ((b'.tag/tinyfile', b'.tag/obj'),
                          (b'.tag/tree-1', b'.tag/obj'),
                          (b'.tag/commit-1', b'.tag/obj')):
                exr = run_get(get_disposition, flavor, (item, b'.tag/obj'), given=given)
                wvpassne(0, exr.rc)
                verify_rx(br'cannot overwrite existing tag', exr.err)
            
    wvstart(get_disposition + ' ' + flavormsg + ' commit/save to tag')
    for item in (b'.tag/commit-2', b'src/' + save_2):
        exr = run_get(get_disposition, flavor, (item, b'.tag/obj'))
        wvpasseq(0, exr.rc)
        validate_clean_repo()
        validate_new_tagged_commit(b'obj', commit_2_id, tree_2_id, exr.out)
        verify_only_refs(heads=[], tags=(b'obj',))
         
    wvstart(get_disposition + ' ' + flavormsg + ' commit/save to branch')
    for item in (b'.tag/commit-2', b'src/' + save_2):
        for given in (None, (b'.tag/commit-1', b'obj'), (b'.tag/commit-2', b'obj')):
            exr = run_get(get_disposition, flavor, (item, b'obj'), given=given)
            wvpasseq(0, exr.rc)
            validate_clean_repo()
            validate_new_save(b'obj/latest', getcwd() + b'/src',
                              commit_2_id, tree_2_id, b'src-2', exr.out)
            verify_only_refs(heads=(b'obj',), tags=[])

    wvstart(get_disposition + ' ' + flavormsg
            + ' commit/save unrelated commit to branch')
    for item in(b'.tag/commit-2', b'src/' + save_2):
        exr = run_get(get_disposition, flavor, (item, b'obj'),
                      given=(b'unrelated-branch', b'obj'))
        wvpasseq(0, exr.rc)
        validate_clean_repo()
        validate_new_save(b'obj/latest', getcwd() + b'/src',
                          commit_2_id, tree_2_id, b'src-2', exr.out)
        verify_only_refs(heads=(b'obj',), tags=[])

    wvstart(get_disposition + ' ' + flavormsg + ' commit/save ancestor to branch')
    save_1 = src_info['save-1']
    commit_1_id = src_info['commit-1-id']
    tree_1_id = src_info['tree-1-id']
    for item in (b'.tag/commit-1', b'src/' + save_1):
        exr = run_get(get_disposition, flavor, (item, b'obj'),
                      given=(b'.tag/commit-2', b'obj'))
        wvpasseq(0, exr.rc)
        validate_clean_repo()
        validate_new_save(b'obj/latest', getcwd() + b'/src',
                          commit_1_id, tree_1_id, b'src-1', exr.out)
        verify_only_refs(heads=(b'obj',), tags=[])


    wvstart(get_disposition + ' ' + flavormsg + ', implicit destinations')
    exr = run_get(get_disposition, flavor, b'.tag/commit-2')
    wvpasseq(0, exr.rc)
    validate_clean_repo()
    validate_new_tagged_commit(b'commit-2', commit_2_id, tree_2_id, exr.out)
    verify_only_refs(heads=[], tags=(b'commit-2',))

    exr = run_get(get_disposition, flavor, b'src/latest')
    wvpasseq(0, exr.rc)
    validate_clean_repo()
    validate_new_save(b'src/latest', getcwd() + b'/src',
                      commit_2_id, tree_2_id, b'src-2', exr.out)
    verify_only_refs(heads=(b'src',), tags=[])

def _test_pick_force(get_disposition, src_info):
    _test_pick_common(get_disposition, src_info, force=True)

def _test_pick_noforce(get_disposition, src_info):
    _test_pick_common(get_disposition, src_info, force=False)

def _test_new_tag(get_disposition, src_info):
    tinyfile_id = src_info['tinyfile-id']
    tinyfile_path = src_info['tinyfile-path']
    commit_2_id = src_info['commit-2-id']
    tree_2_id = src_info['tree-2-id']
    subtree_id = src_info['subtree-id']
    subtree_vfs_path = src_info['subtree-vfs-path']

    wvstart(get_disposition + ' --new-tag to root fails')
    for item in (b'.tag/tinyfile',
                 b'src/latest' + tinyfile_path,
                 b'.tag/subtree',
                 b'src/latest' + subtree_vfs_path,
                 b'.tag/commit-1',
                 b'src/latest',
                 b'src'):
        exr = run_get(get_disposition, b'--new-tag', (item, b'/'))
        wvpassne(0, exr.rc)
        verify_rx(br'destination for .+ must be a VFS tag', exr.err)

    # Anything to new tag.
    wvstart(get_disposition + ' --new-tag, blob tag')
    for item in (b'.tag/tinyfile', b'src/latest' + tinyfile_path):
        exr = run_get(get_disposition, b'--new-tag', (item, b'.tag/obj'))
        wvpasseq(0, exr.rc)        
        validate_blob(tinyfile_id, tinyfile_id)
        verify_only_refs(heads=[], tags=(b'obj',))

    wvstart(get_disposition + ' --new-tag, tree tag')
    for item in (b'.tag/subtree', b'src/latest' + subtree_vfs_path):
        exr = run_get(get_disposition, b'--new-tag', (item, b'.tag/obj'))
        wvpasseq(0, exr.rc)        
        validate_tree(subtree_id, subtree_id)
        verify_only_refs(heads=[], tags=(b'obj',))
        
    wvstart(get_disposition + ' --new-tag, committish tag')
    for item in (b'.tag/commit-2', b'src/latest', b'src'):
        exr = run_get(get_disposition, b'--new-tag', (item, b'.tag/obj'))
        wvpasseq(0, exr.rc)        
        validate_tagged_save(b'obj', getcwd() + b'/src/', commit_2_id, tree_2_id,
                             b'src-2', exr.out)
        verify_only_refs(heads=[], tags=(b'obj',))

    # Anything to existing tag (fails).
    for ex_type, ex_tag in (('blob', (b'.tag/tinyfile', b'.tag/obj')),
                            ('tree', (b'.tag/tree-1', b'.tag/obj')),
                            ('commit', (b'.tag/commit-1', b'.tag/obj'))):
        for item_type, item in (('blob tag', b'.tag/tinyfile'),
                                ('blob path', b'src/latest' + tinyfile_path),
                                ('tree tag', b'.tag/subtree'),
                                ('tree path', b'src/latest' + subtree_vfs_path),
                                ('commit tag', b'.tag/commit-2'),
                                ('save', b'src/latest'),
                                ('branch', b'src')):
            wvstart(get_disposition + ' --new-tag of ' + item_type
                    + ', given existing ' + ex_type + ' tag, fails')
            exr = run_get(get_disposition, b'--new-tag', (item, b'.tag/obj'),
                          given=ex_tag)
            wvpassne(0, exr.rc)
            verify_rx(br'cannot overwrite existing tag .* \(requires --replace\)',
                      exr.err)

    # Anything to branch (fails).
    for ex_type, ex_tag in (('nothing', None),
                            ('blob', (b'.tag/tinyfile', b'.tag/obj')),
                            ('tree', (b'.tag/tree-1', b'.tag/obj')),
                            ('commit', (b'.tag/commit-1', b'.tag/obj'))):
        for item_type, item in (('blob tag', b'.tag/tinyfile'),
                ('blob path', b'src/latest' + tinyfile_path),
                ('tree tag', b'.tag/subtree'),
                ('tree path', b'src/latest' + subtree_vfs_path),
                ('commit tag', b'.tag/commit-2'),
                ('save', b'src/latest'),
                ('branch', b'src')):
            wvstart(get_disposition + ' --new-tag to branch of ' + item_type
                    + ', given existing ' + ex_type + ' tag, fails')
            exr = run_get(get_disposition, b'--new-tag', (item, b'obj'),
                          given=ex_tag)
            wvpassne(0, exr.rc)
            verify_rx(br'destination for .+ must be a VFS tag', exr.err)

    wvstart(get_disposition + ' --new-tag, implicit destinations')
    exr = run_get(get_disposition, b'--new-tag', b'.tag/commit-2')
    wvpasseq(0, exr.rc)        
    validate_tagged_save(b'commit-2', getcwd() + b'/src/', commit_2_id, tree_2_id,
                         b'src-2', exr.out)
    verify_only_refs(heads=[], tags=(b'commit-2',))

def _test_unnamed(get_disposition, src_info):
    tinyfile_id = src_info['tinyfile-id']
    tinyfile_path = src_info['tinyfile-path']
    subtree_vfs_path = src_info['subtree-vfs-path']
    wvstart(get_disposition + ' --unnamed to root fails')
    for item in (b'.tag/tinyfile',
                 b'src/latest' + tinyfile_path,
                 b'.tag/subtree',
                 b'src/latest' + subtree_vfs_path,
                 b'.tag/commit-1',
                 b'src/latest',
                 b'src'):
        for ex_ref in (None, (item, b'.tag/obj')):
            exr = run_get(get_disposition, b'--unnamed', (item, b'/'),
                          given=ex_ref)
            wvpassne(0, exr.rc)
            verify_rx(br'usage: bup get ', exr.err)

    wvstart(get_disposition + ' --unnamed file')
    for item in (b'.tag/tinyfile', b'src/latest' + tinyfile_path):
        exr = run_get(get_disposition, b'--unnamed', item)
        wvpasseq(0, exr.rc)        
        validate_blob(tinyfile_id, tinyfile_id)
        verify_only_refs(heads=[], tags=[])

        exr = run_get(get_disposition, b'--unnamed', item,
                      given=(item, b'.tag/obj'))
        wvpasseq(0, exr.rc)        
        validate_blob(tinyfile_id, tinyfile_id)
        verify_only_refs(heads=[], tags=(b'obj',))

    wvstart(get_disposition + ' --unnamed tree')
    subtree_id = src_info['subtree-id']
    for item in (b'.tag/subtree', b'src/latest' + subtree_vfs_path):
        exr = run_get(get_disposition, b'--unnamed', item)
        wvpasseq(0, exr.rc)        
        validate_tree(subtree_id, subtree_id)
        verify_only_refs(heads=[], tags=[])
        
        exr = run_get(get_disposition, b'--unnamed', item,
                      given=(item, b'.tag/obj'))
        wvpasseq(0, exr.rc)        
        validate_tree(subtree_id, subtree_id)
        verify_only_refs(heads=[], tags=(b'obj',))
        
    wvstart(get_disposition + ' --unnamed committish')
    save_2 = src_info['save-2']
    commit_2_id = src_info['commit-2-id']
    for item in (b'.tag/commit-2', b'src/' + save_2, b'src'):
        exr = run_get(get_disposition, b'--unnamed', item)
        wvpasseq(0, exr.rc)        
        validate_commit(commit_2_id, commit_2_id)
        verify_only_refs(heads=[], tags=[])

        exr = run_get(get_disposition, b'--unnamed', item,
                      given=(item, b'.tag/obj'))
        wvpasseq(0, exr.rc)        
        validate_commit(commit_2_id, commit_2_id)
        verify_only_refs(heads=[], tags=(b'obj',))

def create_get_src():
    global bup_cmd, src_info
    wvstart('preparing')
    ex((bup_cmd, b'-d', b'get-src', b'init'))

    mkdir(b'src')
    open(b'src/unrelated', 'a').close()
    ex((bup_cmd, b'-d', b'get-src', b'index', b'src'))
    ex((bup_cmd, b'-d', b'get-src', b'save', b'-tcn', b'unrelated-branch', b'src'))

    ex((bup_cmd, b'-d', b'get-src', b'index', b'--clear'))
    rmrf(b'src')
    mkdir(b'src')
    open(b'src/zero', 'a').close()
    ex((bup_cmd, b'-d', b'get-src', b'index', b'src'))
    exr = exo((bup_cmd, b'-d', b'get-src', b'save', b'-tcn', b'src', b'src'))
    out = exr.out.splitlines()
    tree_0_id = out[0]
    commit_0_id = out[-1]
    exr = exo((bup_cmd, b'-d', b'get-src', b'ls', b'src'))
    save_0 = exr.out.splitlines()[0]
    ex((b'git', b'--git-dir', b'get-src', b'branch', b'src-0', b'src'))
    ex((b'cp', b'-RPp', b'src', b'src-0'))
    
    rmrf(b'src')
    mkdir(b'src')
    mkdir(b'src/x')
    mkdir(b'src/x/y')
    ex((bup_cmd + b' -d get-src random 1k > src/1'), shell=True)
    ex((bup_cmd + b' -d get-src random 1k > src/x/2'), shell=True)
    ex((bup_cmd, b'-d', b'get-src', b'index', b'src'))
    exr = exo((bup_cmd, b'-d', b'get-src', b'save', b'-tcn', b'src', b'src'))
    out = exr.out.splitlines()
    tree_1_id = out[0]
    commit_1_id = out[-1]
    exr = exo((bup_cmd, b'-d', b'get-src', b'ls', b'src'))
    save_1 = exr.out.splitlines()[1]
    ex((b'git', b'--git-dir', b'get-src', b'branch', b'src-1', b'src'))
    ex((b'cp', b'-RPp', b'src', b'src-1'))
    
    # Make a copy the current state of src so we'll have an ancestor.
    ex((b'cp', b'-RPp',
         b'get-src/refs/heads/src', b'get-src/refs/heads/src-ancestor'))

    with open(b'src/tiny-file', 'ab') as f: f.write(b'xyzzy')
    ex((bup_cmd, b'-d', b'get-src', b'index', b'src'))
    ex((bup_cmd, b'-d', b'get-src', b'tick'))  # Ensure the save names differ
    exr = exo((bup_cmd, b'-d', b'get-src', b'save', b'-tcn', b'src', b'src'))
    out = exr.out.splitlines()
    tree_2_id = out[0]
    commit_2_id = out[-1]
    exr = exo((bup_cmd, b'-d', b'get-src', b'ls', b'src'))
    save_2 = exr.out.splitlines()[2]
    rename(b'src', b'src-2')

    src_root = getcwd() + b'/src'

    subtree_path = b'src-2/x'
    subtree_vfs_path = src_root + b'/x'

    # No support for "ls -d", so grep...
    exr = exo((bup_cmd, b'-d', b'get-src', b'ls', b'-s', b'src/latest' + src_root))
    out = exr.out.splitlines()
    subtree_id = None
    for line in out:
        if b'x' in line:
            subtree_id = line.split()[0]
    assert(subtree_id)

    # With a tiny file, we'll get a single blob, not a chunked tree
    tinyfile_path = src_root + b'/tiny-file'
    exr = exo((bup_cmd, b'-d', b'get-src', b'ls', b'-s', b'src/latest' + tinyfile_path))
    tinyfile_id = exr.out.splitlines()[0].split()[0]

    ex((bup_cmd, b'-d', b'get-src', b'tag', b'tinyfile', tinyfile_id))
    ex((bup_cmd, b'-d', b'get-src', b'tag', b'subtree', subtree_id))
    ex((bup_cmd, b'-d', b'get-src', b'tag', b'tree-0', tree_0_id))
    ex((bup_cmd, b'-d', b'get-src', b'tag', b'tree-1', tree_1_id))
    ex((bup_cmd, b'-d', b'get-src', b'tag', b'tree-2', tree_2_id))
    ex((bup_cmd, b'-d', b'get-src', b'tag', b'commit-0', commit_0_id))
    ex((bup_cmd, b'-d', b'get-src', b'tag', b'commit-1', commit_1_id))
    ex((bup_cmd, b'-d', b'get-src', b'tag', b'commit-2', commit_2_id))
    ex((b'git', b'--git-dir', b'get-src', b'branch', b'commit-1', commit_1_id))
    ex((b'git', b'--git-dir', b'get-src', b'branch', b'commit-2', commit_2_id))

    return {'tinyfile-path' : tinyfile_path,
            'tinyfile-id' : tinyfile_id,
            'subtree-id' : subtree_id,
            'tree-0-id' : tree_0_id,
            'tree-1-id' : tree_1_id,
            'tree-2-id' : tree_2_id,
            'commit-0-id' : commit_0_id,
            'commit-1-id' : commit_1_id,
            'commit-2-id' : commit_2_id,
            'save-1' : save_1,
            'save-2' : save_2,
            'subtree-path' : subtree_path,
            'subtree-vfs-path' : subtree_vfs_path}
    
# FIXME: this fails in a strange way:
#   WVPASS given nothing get --ff not-there

dispositions_to_test = ('get',)

if int(environ.get(b'BUP_TEST_LEVEL', b'0')) >= 11:
    dispositions_to_test += ('get-on', 'get-to')

categories = ('replace', 'universal', 'ff', 'append', 'pick_force', 'pick_noforce', 'new_tag', 'unnamed')

@pytest.mark.parametrize("disposition,category", product(dispositions_to_test, categories))
def test_get(tmpdir, disposition, category):
    chdir(tmpdir)
    try:
        src_info = create_get_src()
        globals().get('_test_' + category)(disposition, src_info)
    finally:
        chdir(top)
