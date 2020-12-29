#!/bin/sh
"""": # -*-python-*-
# https://sourceware.org/bugzilla/show_bug.cgi?id=26034
export "BUP_ARGV_0"="$0"
arg_i=1
for arg in "$@"; do
    export "BUP_ARGV_${arg_i}"="$arg"
    shift
    arg_i=$((arg_i + 1))
done
# Here to end of preamble replaced during install
bup_python="$(dirname "$0")/../../config/bin/python" || exit $?
exec "$bup_python" "$0"
"""
# end of bup preamble

from __future__ import absolute_import, print_function
import os, re, stat, sys, textwrap, time
from binascii import hexlify, unhexlify
from collections import namedtuple
from functools import partial
from stat import S_ISDIR

sys.path[:0] = [os.path.dirname(os.path.realpath(__file__)) + '/..']

from bup import compat, git, client, helpers, vfs
from bup.compat import argv_bytes, environ, hexstr, items, wrap_main
from bup.git import get_cat_data, parse_commit, walk_object
from bup.helpers import add_error, debug1, handle_ctrl_c, log, saved_errors
from bup.helpers import hostname, shstr, tty_width
from bup.io import path_msg
from bup.pwdgrp import userfullname, username
from bup.repo import LocalRepo, RemoteRepo

argspec = (
    "usage: bup get [-s source] [-r remote] (<--ff|--append|...> REF [DEST])...",

    """Transfer data from a source repository to a destination repository
    according to the methods specified (--ff, --ff:, --append, etc.).
    Both repositories default to BUP_DIR.  A remote destination may be
    specified with -r, and data may be pulled from a remote repository
    with the related "bup on HOST get ..." command.""",

    ('optional arguments:',
     (('-h, --help', 'show this help message and exit'),
      ('-v, --verbose',
       'increase log output (can be specified more than once)'),
      ('-q, --quiet', "don't show progress meter"),
      ('-s SOURCE, --source SOURCE',
       'path to the source repository (defaults to BUP_DIR)'),
      ('-r REMOTE, --remote REMOTE',
       'hostname:/path/to/repo of remote destination repository'),
      ('-t --print-trees', 'output a tree id for each ref set'),
      ('-c, --print-commits', 'output a commit id for each ref set'),
      ('--print-tags', 'output an id for each tag'),
      ('--bwlimit BWLIMIT', 'maximum bytes/sec to transmit to server'),
      ('-0, -1, -2, -3, -4, -5, -6, -7, -8, -9, --compress LEVEL',
       'set compression LEVEL (default: 1)'))),

    ('transfer methods:',
     (('--ff REF, --ff: REF DEST',
       'fast-forward dest REF (or DEST) to match source REF'),
      ('--append REF, --append: REF DEST',
       'append REF (treeish or committish) to dest REF (or DEST)'),
      ('--pick REF, --pick: REF DEST',
       'append single source REF commit to dest REF (or DEST)'),
      ('--force-pick REF, --force-pick: REF DEST',
       '--pick, overwriting REF (or DEST)'),
      ('--new-tag REF, --new-tag: REF DEST',
       'tag source ref REF as REF (or DEST) in dest unless it already exists'),
      ('--replace, --replace: REF DEST',
       'overwrite REF (or DEST) in dest with source REF'),
      ('--unnamed REF',
       'fetch REF anonymously (without destination ref)'))))

def render_opts(opts, width=None):
    if not width:
        width = tty_width()
    result = []
    for args, desc in opts:
        result.append(textwrap.fill(args, width=width,
                                    initial_indent=(' ' * 2),
                                    subsequent_indent=(' ' * 4)))
        result.append('\n')
        result.append(textwrap.fill(desc, width=width,
                                    initial_indent=(' ' * 6),
                                    subsequent_indent=(' ' * 6)))
        result.append('\n')
    return result

def usage(argspec, width=None):
    if not width:
        width = tty_width()
    usage, preamble, groups = argspec[0], argspec[1], argspec[2:]
    msg = []
    msg.append(textwrap.fill(usage, width=width, subsequent_indent='  '))
    msg.append('\n\n')
    msg.append(textwrap.fill(preamble.replace('\n', ' '), width=width))
    msg.append('\n')
    for group_name, group_args in groups:
        msg.extend(['\n', group_name, '\n'])
        msg.extend(render_opts(group_args, width=width))
    return ''.join(msg)

def misuse(message=None):
    sys.stderr.write(usage(argspec))
    if message:
        sys.stderr.write('\nerror: ')
        sys.stderr.write(message)
        sys.stderr.write('\n')
    sys.exit(1)

def require_n_args_or_die(n, args):
    if len(args) < n + 1:
        misuse('%s argument requires %d %s'
               % (n, 'values' if n == 1 else 'value'))
    result = args[1:1+n], args[1+n:]
    assert len(result[0]) == n
    return result

Spec = namedtuple('Spec', ('method', 'src', 'dest'))

def spec_msg(s):
    if not s.dest:
        return '--%s %s' % (s.method, path_msg(s.src))
    return '--%s: %s %s' % (s.method, path_msg(s.src), path_msg(s.dest))

def parse_args(args):
    class GetOpts:
        pass
    opt = GetOpts()
    opt.help = False
    opt.verbose = 0
    opt.quiet = False
    opt.print_commits = opt.print_trees = opt.print_tags = False
    opt.bwlimit = None
    opt.compress = 1
    opt.source = opt.remote = None
    opt.target_specs = []

    remaining = args[1:]  # Skip argv[0]
    while remaining:
        arg = remaining[0]
        if arg in ('-h', '--help'):
            sys.stdout.write(usage(argspec))
            sys.exit(0)
        elif arg in ('-v', '--verbose'):
            opt.verbose += 1
            remaining = remaining[1:]
        elif arg in ('--ff', '--append', '--pick', '--force-pick',
                     '--new-tag', '--replace', '--unnamed'):
            (ref,), remaining = require_n_args_or_die(1, remaining)
            ref = argv_bytes(ref)
            opt.target_specs.append(Spec(method=arg[2:], src=ref, dest=None))
        elif arg in ('--ff:', '--append:', '--pick:', '--force-pick:',
                     '--new-tag:', '--replace:'):
            (ref, dest), remaining = require_n_args_or_die(2, remaining)
            ref, dest = argv_bytes(ref), argv_bytes(dest)
            opt.target_specs.append(Spec(method=arg[2:-1], src=ref, dest=dest))
        elif arg in ('-s', '--source'):
            (opt.source,), remaining = require_n_args_or_die(1, remaining)
        elif arg in ('-r', '--remote'):
            (opt.remote,), remaining = require_n_args_or_die(1, remaining)
        elif arg in ('-c', '--print-commits'):
            opt.print_commits, remaining = True, remaining[1:]
        elif arg in ('-t', '--print-trees'):
            opt.print_trees, remaining = True, remaining[1:]
        elif arg == '--print-tags':
            opt.print_tags, remaining = True, remaining[1:]
        elif arg in ('-0', '-1', '-2', '-3', '-4', '-5', '-6', '-7', '-8', '-9'):
            opt.compress = int(arg[1:])
            remaining = remaining[1:]
        elif arg == '--compress':
            (opt.compress,), remaining = require_n_args_or_die(1, remaining)
            opt.compress = int(opt.compress)
        elif arg == '--bwlimit':
            (opt.bwlimit,), remaining = require_n_args_or_die(1, remaining)
            opt.bwlimit = long(opt.bwlimit)
        elif arg.startswith('-') and len(arg) > 2 and arg[1] != '-':
            # Try to interpret this as -xyz, i.e. "-xyz -> -x -y -z".
            # We do this last so that --foo -bar is valid if --foo
            # requires a value.
            remaining[0:1] = ('-' + c for c in arg[1:])
            # FIXME
            continue
        else:
            misuse()
    return opt

# FIXME: client error handling (remote exceptions, etc.)

# FIXME: walk_object in in git.py doesn't support opt.verbose.  Do we
# need to adjust for that here?
def get_random_item(name, hash, repo, writer, opt):
    def already_seen(oid):
        return writer.exists(unhexlify(oid))
    for item in walk_object(repo.cat, hash, stop_at=already_seen,
                            include_data=True):
        # already_seen ensures that writer.exists(id) is false.
        # Otherwise, just_write() would fail.
        writer.just_write(item.oid, item.type, item.data)


def append_commit(name, hash, parent, src_repo, writer, opt):
    now = time.time()
    items = parse_commit(get_cat_data(src_repo.cat(hash), b'commit'))
    tree = unhexlify(items.tree)
    author = b'%s <%s>' % (items.author_name, items.author_mail)
    author_time = (items.author_sec, items.author_offset)
    committer = b'%s <%s@%s>' % (userfullname(), username(), hostname())
    get_random_item(name, hexlify(tree), src_repo, writer, opt)
    c = writer.new_commit(tree, parent,
                          author, items.author_sec, items.author_offset,
                          committer, now, None,
                          items.message)
    return c, tree


def append_commits(commits, src_name, dest_hash, src_repo, writer, opt):
    last_c, tree = dest_hash, None
    for commit in commits:
        last_c, tree = append_commit(src_name, commit, last_c,
                                     src_repo, writer, opt)
    assert(tree is not None)
    return last_c, tree

Loc = namedtuple('Loc', ['type', 'hash', 'path'])
default_loc = Loc(None, None, None)

def find_vfs_item(name, repo):
    res = repo.resolve(name, follow=False, want_meta=False)
    leaf_name, leaf_item = res[-1]
    if not leaf_item:
        return None
    kind = type(leaf_item)
    if kind == vfs.Root:
        kind = 'root'
    elif kind == vfs.Tags:
        kind = 'tags'
    elif kind == vfs.RevList:
        kind = 'branch'
    elif kind == vfs.Commit:
        if len(res) > 1 and type(res[-2][1]) == vfs.RevList:
            kind = 'save'
        else:
            kind = 'commit'
    elif kind == vfs.Item:
        if S_ISDIR(vfs.item_mode(leaf_item)):
            kind = 'tree'
        else:
            kind = 'blob'
    elif kind == vfs.Chunky:
        kind = 'tree'
    elif kind == vfs.FakeLink:
        # Don't have to worry about ELOOP, excepting malicious
        # remotes, since "latest" is the only FakeLink.
        assert leaf_name == b'latest'
        res = repo.resolve(leaf_item.target, parent=res[:-1],
                           follow=False, want_meta=False)
        leaf_name, leaf_item = res[-1]
        assert leaf_item
        assert type(leaf_item) == vfs.Commit
        name = b'/'.join(x[0] for x in res)
        kind = 'save'
    else:
        raise Exception('unexpected resolution for %s: %r'
                        % (path_msg(name), res))
    path = b'/'.join(name for name, item in res)
    if hasattr(leaf_item, 'coid'):
        result = Loc(type=kind, hash=leaf_item.coid, path=path)
    elif hasattr(leaf_item, 'oid'):
        result = Loc(type=kind, hash=leaf_item.oid, path=path)
    else:
        result = Loc(type=kind, hash=None, path=path)
    return result


Target = namedtuple('Target', ['spec', 'src', 'dest'])

def loc_desc(loc):
    if loc and loc.hash:
        loc = loc._replace(hash=hexlify(loc.hash))
    return repr(loc)


# FIXME: see if resolve() means we can drop the vfs path cleanup

def cleanup_vfs_path(p):
    result = os.path.normpath(p)
    if result.startswith(b'/'):
        return result
    return b'/' + result


def validate_vfs_path(p):
    if p.startswith(b'/.') \
       and not p.startswith(b'/.tag/'):
        misuse('unsupported destination path %s in %s'
               % (path_msg(dest.path), spec_msg(spec)))
    return p


def resolve_src(spec, src_repo):
    src = find_vfs_item(spec.src, src_repo)
    spec_args = spec_msg(spec)
    if not src:
        misuse('cannot find source for %s' % spec_args)
    if src.type == 'root':
        misuse('cannot fetch entire repository for %s' % spec_args)
    if src.type == 'tags':
        misuse('cannot fetch entire /.tag directory for %s' % spec_args)
    debug1('src: %s\n' % loc_desc(src))
    return src


def get_save_branch(repo, path):
    res = repo.resolve(path, follow=False, want_meta=False)
    leaf_name, leaf_item = res[-1]
    if not leaf_item:
        misuse('error: cannot access %r in %r' % (leaf_name, path))
    assert len(res) == 3
    res_path = b'/'.join(name for name, item in res[:-1])
    return res_path


def resolve_branch_dest(spec, src, src_repo, dest_repo):
    # Resulting dest must be treeish, or not exist.
    if not spec.dest:
        # Pick a default dest.
        if src.type == 'branch':
            spec = spec._replace(dest=spec.src)
        elif src.type == 'save':
            spec = spec._replace(dest=get_save_branch(src_repo, spec.src))
        elif src.path.startswith(b'/.tag/'):  # Dest defaults to the same.
            spec = spec._replace(dest=spec.src)

    spec_args = spec_msg(spec)
    if not spec.dest:
        misuse('no destination (implicit or explicit) for %s', spec_args)

    dest = find_vfs_item(spec.dest, dest_repo)
    if dest:
        if dest.type == 'commit':
            misuse('destination for %s is a tagged commit, not a branch'
                  % spec_args)
        if dest.type != 'branch':
            misuse('destination for %s is a %s, not a branch'
                  % (spec_args, dest.type))
    else:
        dest = default_loc._replace(path=cleanup_vfs_path(spec.dest))

    if dest.path.startswith(b'/.'):
        misuse('destination for %s must be a valid branch name' % spec_args)

    debug1('dest: %s\n' % loc_desc(dest))
    return spec, dest


def resolve_ff(spec, src_repo, dest_repo):
    src = resolve_src(spec, src_repo)
    spec_args = spec_msg(spec)
    if src.type == 'tree':
        misuse('%s is impossible; can only --append a tree to a branch'
              % spec_args)
    if src.type not in ('branch', 'save', 'commit'):
        misuse('source for %s must be a branch, save, or commit, not %s'
              % (spec_args, src.type))
    spec, dest = resolve_branch_dest(spec, src, src_repo, dest_repo)
    return Target(spec=spec, src=src, dest=dest)


def handle_ff(item, src_repo, writer, opt):
    assert item.spec.method == 'ff'
    assert item.src.type in ('branch', 'save', 'commit')
    src_oidx = hexlify(item.src.hash)
    dest_oidx = hexlify(item.dest.hash) if item.dest.hash else None
    if not dest_oidx or dest_oidx in src_repo.rev_list(src_oidx):
        # Can fast forward.
        get_random_item(item.spec.src, src_oidx, src_repo, writer, opt)
        commit_items = parse_commit(get_cat_data(src_repo.cat(src_oidx), b'commit'))
        return item.src.hash, unhexlify(commit_items.tree)
    misuse('destination is not an ancestor of source for %s'
           % spec_msg(item.spec))


def resolve_append(spec, src_repo, dest_repo):
    src = resolve_src(spec, src_repo)
    if src.type not in ('branch', 'save', 'commit', 'tree'):
        misuse('source for %s must be a branch, save, commit, or tree, not %s'
              % (spec_msg(spec), src.type))
    spec, dest = resolve_branch_dest(spec, src, src_repo, dest_repo)
    return Target(spec=spec, src=src, dest=dest)


def handle_append(item, src_repo, writer, opt):
    assert item.spec.method == 'append'
    assert item.src.type in ('branch', 'save', 'commit', 'tree')
    assert item.dest.type == 'branch' or not item.dest.type
    src_oidx = hexlify(item.src.hash)
    if item.src.type == 'tree':
        get_random_item(item.spec.src, src_oidx, src_repo, writer, opt)
        parent = item.dest.hash
        msg = b'bup save\n\nGenerated by command:\n%r\n' % compat.argvb
        userline = b'%s <%s@%s>' % (userfullname(), username(), hostname())
        now = time.time()
        commit = writer.new_commit(item.src.hash, parent,
                                   userline, now, None,
                                   userline, now, None, msg)
        return commit, item.src.hash
    commits = list(src_repo.rev_list(src_oidx))
    commits.reverse()
    return append_commits(commits, item.spec.src, item.dest.hash,
                          src_repo, writer, opt)


def resolve_pick(spec, src_repo, dest_repo):
    src = resolve_src(spec, src_repo)
    spec_args = spec_msg(spec)
    if src.type == 'tree':
        misuse('%s is impossible; can only --append a tree' % spec_args)
    if src.type not in ('commit', 'save'):
        misuse('%s impossible; can only pick a commit or save, not %s'
              % (spec_args, src.type))
    if not spec.dest:
        if src.path.startswith(b'/.tag/'):
            spec = spec._replace(dest=spec.src)
        elif src.type == 'save':
            spec = spec._replace(dest=get_save_branch(src_repo, spec.src))
    if not spec.dest:
        misuse('no destination provided for %s', spec_args)
    dest = find_vfs_item(spec.dest, dest_repo)
    if not dest:
        cp = validate_vfs_path(cleanup_vfs_path(spec.dest))
        dest = default_loc._replace(path=cp)
    else:
        if not dest.type == 'branch' and not dest.path.startswith(b'/.tag/'):
            misuse('%s destination is not a tag or branch' % spec_args)
        if spec.method == 'pick' \
           and dest.hash and dest.path.startswith(b'/.tag/'):
            misuse('cannot overwrite existing tag for %s (requires --force-pick)'
                  % spec_args)
    return Target(spec=spec, src=src, dest=dest)


def handle_pick(item, src_repo, writer, opt):
    assert item.spec.method in ('pick', 'force-pick')
    assert item.src.type in ('save', 'commit')
    src_oidx = hexlify(item.src.hash)
    if item.dest.hash:
        return append_commit(item.spec.src, src_oidx, item.dest.hash,
                             src_repo, writer, opt)
    return append_commit(item.spec.src, src_oidx, None, src_repo, writer, opt)


def resolve_new_tag(spec, src_repo, dest_repo):
    src = resolve_src(spec, src_repo)
    spec_args = spec_msg(spec)
    if not spec.dest and src.path.startswith(b'/.tag/'):
        spec = spec._replace(dest=src.path)
    if not spec.dest:
        misuse('no destination (implicit or explicit) for %s', spec_args)
    dest = find_vfs_item(spec.dest, dest_repo)
    if not dest:
        dest = default_loc._replace(path=cleanup_vfs_path(spec.dest))
    if not dest.path.startswith(b'/.tag/'):
        misuse('destination for %s must be a VFS tag' % spec_args)
    if dest.hash:
        misuse('cannot overwrite existing tag for %s (requires --replace)'
              % spec_args)
    return Target(spec=spec, src=src, dest=dest)


def handle_new_tag(item, src_repo, writer, opt):
    assert item.spec.method == 'new-tag'
    assert item.dest.path.startswith(b'/.tag/')
    get_random_item(item.spec.src, hexlify(item.src.hash),
                    src_repo, writer, opt)
    return (item.src.hash,)


def resolve_replace(spec, src_repo, dest_repo):
    src = resolve_src(spec, src_repo)
    spec_args = spec_msg(spec)
    if not spec.dest:
        if src.path.startswith(b'/.tag/') or src.type == 'branch':
            spec = spec._replace(dest=spec.src)
    if not spec.dest:
        misuse('no destination provided for %s', spec_args)
    dest = find_vfs_item(spec.dest, dest_repo)
    if dest:
        if not dest.type == 'branch' and not dest.path.startswith(b'/.tag/'):
            misuse('%s impossible; can only overwrite branch or tag'
                  % spec_args)
    else:
        cp = validate_vfs_path(cleanup_vfs_path(spec.dest))
        dest = default_loc._replace(path=cp)
    if not dest.path.startswith(b'/.tag/') \
       and not src.type in ('branch', 'save', 'commit'):
        misuse('cannot overwrite branch with %s for %s' % (src.type, spec_args))
    return Target(spec=spec, src=src, dest=dest)


def handle_replace(item, src_repo, writer, opt):
    assert(item.spec.method == 'replace')
    if item.dest.path.startswith(b'/.tag/'):
        get_random_item(item.spec.src, hexlify(item.src.hash),
                        src_repo, writer, opt)
        return (item.src.hash,)
    assert(item.dest.type == 'branch' or not item.dest.type)
    src_oidx = hexlify(item.src.hash)
    get_random_item(item.spec.src, src_oidx, src_repo, writer, opt)
    commit_items = parse_commit(get_cat_data(src_repo.cat(src_oidx), b'commit'))
    return item.src.hash, unhexlify(commit_items.tree)


def resolve_unnamed(spec, src_repo, dest_repo):
    if spec.dest:
        misuse('destination name given for %s' % spec_msg(spec))
    src = resolve_src(spec, src_repo)
    return Target(spec=spec, src=src, dest=None)


def handle_unnamed(item, src_repo, writer, opt):
    get_random_item(item.spec.src, hexlify(item.src.hash),
                    src_repo, writer, opt)
    return (None,)


def resolve_targets(specs, src_repo, dest_repo):
    resolved_items = []
    common_args = src_repo, dest_repo
    for spec in specs:
        debug1('initial-spec: %r\n' % (spec,))
        if spec.method == 'ff':
            resolved_items.append(resolve_ff(spec, *common_args))
        elif spec.method == 'append':
            resolved_items.append(resolve_append(spec, *common_args))
        elif spec.method in ('pick', 'force-pick'):
            resolved_items.append(resolve_pick(spec, *common_args))
        elif spec.method == 'new-tag':
            resolved_items.append(resolve_new_tag(spec, *common_args))
        elif spec.method == 'replace':
            resolved_items.append(resolve_replace(spec, *common_args))
        elif spec.method == 'unnamed':
            resolved_items.append(resolve_unnamed(spec, *common_args))
        else: # Should be impossible -- prevented by the option parser.
            assert(False)

    # FIXME: check for prefix overlap?  i.e.:
    #   bup get --ff foo --ff: baz foo/bar
    #   bup get --new-tag .tag/foo --new-tag: bar .tag/foo/bar

    # Now that we have all the items, check for duplicate tags.
    tags_targeted = set()
    for item in resolved_items:
        dest_path = item.dest and item.dest.path
        if dest_path:
            assert(dest_path.startswith(b'/'))
            if dest_path.startswith(b'/.tag/'):
                if dest_path in tags_targeted:
                    if item.spec.method not in ('replace', 'force-pick'):
                        misuse('cannot overwrite tag %s via %s' \
                              % (path_msg(dest_path), spec_msg(item.spec)))
                else:
                    tags_targeted.add(dest_path)
    return resolved_items


def log_item(name, type, opt, tree=None, commit=None, tag=None):
    if tag and opt.print_tags:
        print(hexstr(tag))
    if tree and opt.print_trees:
        print(hexstr(tree))
    if commit and opt.print_commits:
        print(hexstr(commit))
    if opt.verbose:
        last = ''
        if type in ('root', 'branch', 'save', 'commit', 'tree'):
            if not name.endswith(b'/'):
                last = '/'
        log('%s%s\n' % (path_msg(name), last))

def main():
    handle_ctrl_c()
    is_reverse = environ.get(b'BUP_SERVER_REVERSE')
    opt = parse_args(compat.argv)
    git.check_repo_or_die()
    if opt.source:
        opt.source = argv_bytes(opt.source)
    if opt.bwlimit:
        client.bwlimit = parse_num(opt.bwlimit)
    if is_reverse and opt.remote:
        misuse("don't use -r in reverse mode; it's automatic")
    if opt.remote:
        opt.remote = argv_bytes(opt.remote)
    if opt.remote or is_reverse:
        dest_repo = RemoteRepo(opt.remote)
    else:
        dest_repo = LocalRepo()

    with dest_repo as dest_repo:
        with LocalRepo(repo_dir=opt.source) as src_repo:
            with dest_repo.new_packwriter(compression_level=opt.compress) as writer:
                # Resolve and validate all sources and destinations,
                # implicit or explicit, and do it up-front, so we can
                # fail before we start writing (for any obviously
                # broken cases).
                target_items = resolve_targets(opt.target_specs,
                                               src_repo, dest_repo)

                updated_refs = {}  # ref_name -> (original_ref, tip_commit(bin))
                no_ref_info = (None, None)

                handlers = {'ff': handle_ff,
                            'append': handle_append,
                            'force-pick': handle_pick,
                            'pick': handle_pick,
                            'new-tag': handle_new_tag,
                            'replace': handle_replace,
                            'unnamed': handle_unnamed}

                for item in target_items:
                    debug1('get-spec: %r\n' % (item.spec,))
                    debug1('get-src: %s\n' % loc_desc(item.src))
                    debug1('get-dest: %s\n' % loc_desc(item.dest))
                    dest_path = item.dest and item.dest.path
                    if dest_path:
                        if dest_path.startswith(b'/.tag/'):
                            dest_ref = b'refs/tags/%s' % dest_path[6:]
                        else:
                            dest_ref = b'refs/heads/%s' % dest_path[1:]
                    else:
                        dest_ref = None

                    dest_hash = item.dest and item.dest.hash
                    orig_ref, cur_ref = updated_refs.get(dest_ref, no_ref_info)
                    orig_ref = orig_ref or dest_hash
                    cur_ref = cur_ref or dest_hash

                    handler = handlers[item.spec.method]
                    item_result = handler(item, src_repo, writer, opt)
                    if len(item_result) > 1:
                        new_id, tree = item_result
                    else:
                        new_id = item_result[0]

                    if not dest_ref:
                        log_item(item.spec.src, item.src.type, opt)
                    else:
                        updated_refs[dest_ref] = (orig_ref, new_id)
                        if dest_ref.startswith(b'refs/tags/'):
                            log_item(item.spec.src, item.src.type, opt, tag=new_id)
                        else:
                            log_item(item.spec.src, item.src.type, opt,
                                     tree=tree, commit=new_id)

        # Only update the refs at the very end, once the writer is
        # closed, so that if something goes wrong above, the old refs
        # will be undisturbed.
        for ref_name, info in items(updated_refs):
            orig_ref, new_ref = info
            try:
                dest_repo.update_ref(ref_name, new_ref, orig_ref)
                if opt.verbose:
                    new_hex = hexlify(new_ref)
                    if orig_ref:
                        orig_hex = hexlify(orig_ref)
                        log('updated %r (%s -> %s)\n' % (ref_name, orig_hex, new_hex))
                    else:
                        log('updated %r (%s)\n' % (ref_name, new_hex))
            except (git.GitError, client.ClientError) as ex:
                add_error('unable to update ref %r: %s' % (ref_name, ex))

    if saved_errors:
        log('WARNING: %d errors encountered while saving.\n' % len(saved_errors))
        sys.exit(1)

wrap_main(main)
