
from binascii import hexlify, unhexlify
from collections import namedtuple
from dataclasses import field, replace as dcreplace
from re import Pattern
from stat import S_ISDIR
from textwrap import fill
from typing import NoReturn, Optional, Union
from uuid import uuid4
import os, re, sys, textwrap, time

from bup import client, compat, git, hashsplit, vfs
from bup.commit import commit_message
from bup.compat import dataclass, dataclass_frozen_for_testing, get_argvb
from bup.git import MissingObject, get_commit_items, walk_object
from bup.helpers import \
    (EXIT_FAILURE,
     EXIT_RECOVERED,
     EXIT_SUCCESS,
     debug1,
     hostname,
     log,
     note_error,
     nullctx,
     parse_num,
     parse_rx_excludes,
     saved_errors,
     tty_width,
     valid_save_name)
from bup.io import path_msg
from bup.pwdgrp import userfullname, username
from bup.repair import valid_repair_id
from bup.repo import \
    (LocalRepo,
     main_repo_location,
     parse_repo_url_arg,
     repo_for_location,
     repo_for_url)
from bup.rewrite import RepairInfo, Rewriter
from bup.url import URL


argspec = (
    "usage: bup get [-s source] [-r remote] (<--ff|--append|...> REF [DEST])...",

    """Transfer data from a source repository to a destination
    repository according to the methods specified (--ff, --ff:,
    --append, etc.).  Both repositories default to BUP_DIR.  A remote
    destination may be specified with -r, and data may be pulled from
    a remote repository with the related "bup on HOST get ..."
    command.  Currently, --exclude-rx and --exclude-rx-from only apply
    to rewrites and repairs, and only --unnamed supports
    "--ignore-missing".""",

    ('optional arguments:',
     (('-h, --help', 'show this help message and exit'),
      ('-v, --verbose',
       'increase log output (can be specified more than once)'),
      ('-q, --quiet', "don't show progress meter"),
      ('-s PATH, -S URL --source PATH, --source-url URL',
       'the source repository (defaults to BUP_DIR)'),
      ('-r REMOTE, --remote REMOTE',
       'hostname:/path/to/repo of remote destination repository'),
      ('-t --print-trees', 'output a tree id for each ref set'),
      ('-c, --print-commits', 'output a commit id for each ref set'),
      ('--print-tags', 'output an id for each tag'),
      ('--copy', 'copy the data (no rewriting or repairs; the default)'),
      ('--rewrite', 'rewrite data according to destination repo settings'),
      ('--repair', 'repair everything possible'),
      ('--repair-id ID', 'repair session identifier (default: UUID v4)'),
      ('--exclude-rx REGEX', 'skip paths matching the unanchored regex (may be repeated)'),
      ('--exclude-rx-from PATH', 'skip --exclude-rx patterns in PATH (may be repeated)'),
      ('--no-excludes', 'forget any preceeding exclude options'),
      ('--bwlimit BWLIMIT', 'maximum bytes/sec to transmit to server'),
      ('--[no-]ignore-missing', 'ignore missing objects (*dangerous*)'),
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

def usage(width=None):
    if not width:
        width = tty_width()
    use, preamble, groups = argspec[0], argspec[1], argspec[2:]
    msg = []
    msg.append(textwrap.fill(use, width=width, subsequent_indent='  '))
    msg.append('\n\n')
    msg.append(textwrap.fill(re.sub(r'\n\s+', r' ', preamble), width=(width - 1)))
    msg.append('\n')
    for group_name, group_args in groups:
        msg.extend(['\n', group_name, '\n'])
        msg.extend(render_opts(group_args, width=width))
    return ''.join(msg)

def misuse(message=None) -> NoReturn:
    sys.stderr.write(usage())
    if message:
        sys.stderr.write('\nerror: ')
        sys.stderr.write(message)
        sys.stderr.write('\n')
    sys.exit(EXIT_FAILURE)

def require_n_args_or_die(n, args):
    if len(args) < n + 1:
        arg = args[0].decode('ascii')
        misuse(f'{arg} argument requires {n} value{"" if n == 1 else "s"}')
    result = args[1:1+n], args[1+n:]
    assert len(result[0]) == n
    return result

@dataclass_frozen_for_testing(slots=True)
class Spec:
    method: str
    src: bytes
    dest: bytes
    ignore_missing: bool
    repair_info: Optional[RepairInfo] = None
    excludes: Optional[list[Pattern]] = None
    rewriter: Optional[Union[bool, Rewriter]] = None
    def __post_init__(self):
        assert not (self.ignore_missing and self.repair_info), \
            (self.ignore_missing, self.repair_info)

def spec_msg(s):
    if not s.dest:
        return '--%s %s' % (s.method, path_msg(s.src))
    return '--%s: %s %s' % (s.method, path_msg(s.src), path_msg(s.dest))

def parse_args(args):
    @dataclass(slots=True)
    class GetOpts:
        help: bool = False
        verbose: int = 0
        quiet: bool = False
        print_commits: bool = False
        print_trees: bool = False
        print_tags: bool = False
        bwlimit: Optional[int] = None
        compress: Optional[int] = None
        source: Optional[bytes] = None
        remote: Optional[bytes] = None
        source_loc: URL = URL(scheme=b'file')
        dst_loc: Optional[Union[URL, client.Config]] = None
        target_specs: list = field(default_factory=list)
    opt = GetOpts()

    # Since we don't want to create a Rewriter until we've finished
    # checking the requests (e.g. are past the resolvers), the spec's
    # rewriter will be set to True to indicate that it needs the real
    # Rewriter once we have it.
    exclude_opts = []
    ignore_missing = False
    # mode: copy rewrite or repair (None implies copy for compatible configs)
    mode = None
    repair_id = None
    def make_spec(method, src, dest):
        assert mode in (None, 'copy', 'rewrite', 'repair'), mode
        nonlocal repair_id
        if ignore_missing:
            if mode == 'repair':
                misuse('--ignore-missing and --repair are incompatible')
            elif mode == 'rewrite':
                misuse('--ignore-missing and --rewrite are incompatible')
            if method != 'unnamed':
                misuse('currently only --unnamed allows --ignore-missing')
        excludes = parse_rx_excludes(exclude_opts, misuse)
        if excludes and not mode in ('rewrite', 'repair'):
            misuse('--exclude-rx or --exclude-rx-from requires --rewrite or --repair')
        # Set rw to None if no opinion has been expressed so we can
        # require you to state what you want when src/dest repository
        # configs differ (see target checks in get_everything).
        rc = None
        if mode in ('rewrite', 'repair'):
            if method not in ('append', 'pick', 'force-pick'):
                misuse(f'--{method} cannot {mode} (only picks and appends)')
            if repair_id is None:
                repair_id = str(uuid4()).encode('ascii')
            rc = RepairInfo(id=repair_id, destructive=(mode == 'repair'),
                            command=get_argvb())
            rw = True
        elif mode == 'copy': # explicitly specified no rewrite/repair
            rw = False
        elif mode is None:
            rw = None
        else:
            raise Exception(f'invalid get target mode {mode!r}')
        return Spec(method=method, src=src, dest=dest, excludes=excludes,
                    rewriter=rw, ignore_missing=ignore_missing, repair_info=rc)

    pending_method_context = {} # dict to preserve insertion order
    remaining = args[1:]  # Skip argv[0]
    while remaining:
        arg = remaining[0]
        if arg in (b'-h', b'--help'):
            sys.stdout.write(usage())
            sys.exit(EXIT_SUCCESS)
        elif arg in (b'-v', b'--verbose'):
            opt.verbose += 1
            remaining = remaining[1:]
        elif arg == b'--copy':
            pending_method_context[arg] = True
            mode, remaining = 'copy', remaining[1:]
        elif arg == b'--repair':
            pending_method_context[arg] = True
            mode, remaining = 'repair', remaining[1:]
        elif arg == b'--ignore-missing':
            pending_method_context[arg] = True
            ignore_missing, remaining = True, remaining[1:]
        elif arg == b'--no-ignore-missing':
            pending_method_context[arg] = True
            ignore_missing, remaining = False, remaining[1:]
        elif arg == b'--repair-id':
            pending_method_context[arg] = True
            (val,), remaining = require_n_args_or_die(1, remaining)
            if not val:
                misuse('empty --repair-id')
            if not valid_repair_id(val):
                misuse('--repair-id must be ASCII without control characters or DEL')
            repair_id = val
        elif arg in (b'--ff', b'--append', b'--pick', b'--force-pick',
                     b'--new-tag', b'--replace', b'--unnamed'):
            (ref,), remaining = require_n_args_or_die(1, remaining)
            opt.target_specs.append(make_spec(method=arg[2:].decode('ascii'),
                                              src=ref, dest=None))
            pending_method_context = {}
        elif arg in (b'--ff:', b'--append:', b'--pick:', b'--force-pick:',
                     b'--new-tag:', b'--replace:'):
            (ref, dest), remaining = require_n_args_or_die(2, remaining)
            opt.target_specs.append(make_spec(method=arg[2:-1].decode('ascii'),
                                              src=ref, dest=dest))
            pending_method_context = {}
        elif arg in (b'-S', b'--source-url'):
            (opt.source,), remaining = require_n_args_or_die(1, remaining)
            opt.source_loc = parse_repo_url_arg('--source-url', opt.source, misuse)
        elif arg in (b'-s', b'--source'):
            (opt.source,), remaining = require_n_args_or_die(1, remaining)
            opt.source_loc = URL(scheme=b'file', path=opt.source)
        elif arg in (b'-r', b'--remote'):
            (opt.remote,), remaining = require_n_args_or_die(1, remaining)
        elif arg in (b'-c', b'--print-commits'):
            opt.print_commits, remaining = True, remaining[1:]
        elif arg in (b'-t', b'--print-trees'):
            opt.print_trees, remaining = True, remaining[1:]
        elif arg == b'--print-tags':
            opt.print_tags, remaining = True, remaining[1:]
        elif arg == b'--rewrite':
            pending_method_context[arg] = True
            mode, remaining = 'rewrite', remaining[1:]
        elif arg in (b'--exclude-rx', b'--exclude-rx-from'): # handled later
            pending_method_context[arg] = True
            (val,), remaining = require_n_args_or_die(1, remaining)
            exclude_opts.append((arg, val))
        elif arg == b'--no-excludes':
            pending_method_context[arg] = True
            exclude_opts, remaining = [], remaining[1:]
        elif arg in (b'-0', b'-1', b'-2', b'-3', b'-4', b'-5', b'-6', b'-7',
                     b'-8', b'-9'):
            opt.compress = int(arg[1:])
            remaining = remaining[1:]
        elif arg == b'--compress':
            (opt.compress,), remaining = require_n_args_or_die(1, remaining)
            opt.compress = int(opt.compress)
        elif arg == b'--bwlimit':
            (opt.bwlimit,), remaining = require_n_args_or_die(1, remaining)
            try:
                opt.bwlimit = parse_num(opt.bwlimit)
            except ValueError as ex:
                misuse(f'invalid --bwlimit ({str(ex)})')
        elif arg.startswith(b'-') and len(arg) > 2 and arg[1] != b'-'[0]:
            # Try to interpret this as -xyz, i.e. "-xyz -> -x -y -z".
            # We do this last so that --foo -bar is valid if --foo
            # requires a value.
            remaining[0:1] = (b'-%c' % c for c in arg[1:])
            # FIXME
            continue
        else:
            misuse(f'unrecognized argument: {path_msg(arg)}')
    if pending_method_context:
        ctx_msg = ' '. join(path_msg(x) for x in pending_method_context)
        misuse(f'trailing arguments with no effect: {ctx_msg}')
    opt.dst_loc = main_repo_location(opt.remote, misuse)
    if not opt.target_specs:
        misuse('no methods specified')
    return opt

# FIXME: client error handling (remote exceptions, etc.)

# FIXME: walk_object in in git.py doesn't support opt.verbose.  Do we
# need to adjust for that here?
def get_random_item(hash, src_repo, dest_repo, ignore_missing):
    def already_seen(oid):
        return dest_repo.exists(unhexlify(oid))
    def get_ref(oidx, include_data=False):
        assert include_data
        return src_repo.cat(oidx)
    for item in walk_object(get_ref, hash, stop_at=already_seen,
                            include_data=True, result='item'):
        assert isinstance(item, git.WalkItem)
        if item.data is False:
            if not ignore_missing:
                raise MissingObject(item.oid)
            note_error(f'skipping missing source object {item.oid.hex()}\n')
            continue
        # We must not just_write() unless we're sure that the oid
        # doesn't writer.exists() *now* or we may cause the server to
        # suggest the same idx more than once, causing
        # client.sync_index() to reject it via an exception.
        #
        # With local repositories, we don't need to recheck existence
        # here because the answer can't have changed, but with remote
        # repositories already_seen() may be false when the tree is
        # first encountered, and then true by the time walk_object()
        # yields it here, due to index-cache changes during the
        # depth-first traversal.
        #
        # That's because in the interim, the client may sync an index
        # from the server that happens to contain the tree, as the
        # result of a "suggestion" from the server after the client
        # attempts to write some other oid that the server already
        # has. Without this check, we can provoke a duplicate index
        # suggestion which then causes client.sync_index() to throw.
        if not isinstance(dest_repo, LocalRepo) and item.type != b'blob' \
           and dest_repo.exists(item.oid):
            continue
        dest_repo.just_write(item.oid, item.type, item.data)


@dataclass_frozen_for_testing(slots=True)
class GetResult:
    oid: Optional[bytes] = None
    tree: Optional[bytes] = None
    repairs: int = 0


@dataclass_frozen_for_testing(slots=True)
class VFSLoc:
    path: bytes
    type: str # find_vfs_item type (see below)
    hash: Optional[bytes] = None # (e.g. None if destination doesn't exist)
    vfs_path: Optional[bytes] = None
    ref: Optional[bytes] = None # associated git ref (heads or tags)
    def __post_init__(self):
        assert self.path, self
        assert isinstance(self.path, bytes)
        assert self.type in ('root', 'tags', 'branch', 'save', 'commit', 'tree',
                             'blob'), \
            self.type


def transfer_commit(hash, parent, src_repo, dest_repo, ignore_missing):
    now = time.time()
    items = get_commit_items(hash, src_repo.cat)
    tree = unhexlify(items.tree)
    author = b'%s <%s>' % (items.author_name, items.author_mail)
    committer = b'%s <%s@%s>' % (userfullname(), username(), hostname())
    get_random_item(hexlify(tree), src_repo, dest_repo, ignore_missing)
    c = dest_repo.write_commit(tree, parent,
                               author, items.author_sec, items.author_offset,
                               committer, now, None,
                               items.message)
    return GetResult(c, tree)


def append_commit(src_loc, parent, src_repo, dest_repo, rewriter, excludes,
                  repair_info, ignore_missing):
    if not rewriter:
        assert isinstance(src_loc, (bytes, VFSLoc)), src_loc
        oidx = src_loc if isinstance(src_loc, bytes) else hexlify(src_loc.hash)
        return transfer_commit(oidx, parent, src_repo, dest_repo,
                               ignore_missing)

    # Friendlier checking was done during resolve_*
    assert isinstance(src_loc, VFSLoc), src_loc
    path = src_loc.vfs_path
    assert len(path) == 3, path
    root_, ref, save = path
    assert isinstance(save[1], (vfs.Commit, vfs.FakeLink)), path
    assert isinstance(ref[1], vfs.RevList), path
    save_oid, tree_oid, repairs = \
        rewriter.append_save(path, parent, src_repo, dest_repo, excludes,
                             repair_info)
    return GetResult(save_oid, tree_oid, repairs.repair_count())

def append_commits(src_loc, dest_hash, src_repo, dest_repo, rewriter, excludes,
                   repair_info, ignore_missing):
    if not rewriter:
        commits = list(src_repo.rev_list(hexlify(src_loc.hash)))
        commits.reverse()
        last_c, tree = dest_hash, None
        for commit in commits:
            res = append_commit(commit, last_c, src_repo, dest_repo, rewriter,
                                excludes, repair_info, ignore_missing)
            last_c = res.oid
            tree = res.tree
            assert res.repairs == 0
        assert tree is not None
        return GetResult(last_c, tree)

    # Friendlier checking was done during resolve_*
    assert isinstance(src_loc, VFSLoc), src_loc
    assert src_loc.type in ('branch', 'commit', 'save'), src_loc
    path = src_loc.vfs_path
    assert len(path) == 2, path # root, ref
    ref = path[1]
    assert isinstance(ref[1], vfs.RevList), ref[1]

    # We need both the VFS name (YYYY-MM-DD[-N]), and the rev-list
    # order, so for now, cross-reference rev-list with contents().
    # Refusing metadata allows us to handle/repair missing trees, root
    # .bupms, etc. if we're repairing.
    entry_for_coid = {}
    for entry in vfs.contents(src_repo, path[1][1], want_meta=False):
        if entry[0] in (b'.', b'..', b'latest'):
            continue
        entry_for_coid[entry[1].coid] = entry

    commits = list(src_repo.rev_list(hexlify(src_loc.hash)))
    commits.reverse()

    last_c, tree, repair_count = dest_hash, None, 0
    for commit in commits:
        coid = unhexlify(commit)
        last_c, tree, repairs = \
            rewriter.append_save(path + (entry_for_coid[coid],), last_c,
                                 src_repo, dest_repo, excludes, repair_info)
        repair_count += repairs.repair_count()
    assert tree is not None
    return GetResult(last_c, tree, repair_count)


GitLoc = namedtuple('GitLoc', ('ref', 'hash', 'type'))

def find_git_item(ref, repo):
    oidx, typ, _, it = repo.cat(ref)
    # FIXME: don't include_data once repo supports it
    for _ in it: pass
    if not oidx:
        return None
    return GitLoc(ref, unhexlify(oidx), typ)


def find_vfs_item(name, repo):
    # cf. VFSLoc.__post_init__ when changing the set of types
    res = repo.resolve(name, follow=False, want_meta=False)
    leaf_name, leaf_item = res[-1]
    if not leaf_item:
        return None
    vfs_path = res
    kind = type(leaf_item)
    if kind == vfs.Root:
        kind = 'root'
    elif kind == vfs.Tags:
        kind = 'tags'
    elif kind == vfs.RevList:
        kind = 'branch'
    elif kind == vfs.Commit:
        if len(res) > 1 and isinstance(res[-2][1], vfs.RevList):
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
        assert isinstance(leaf_item, vfs.Commit)
        name = b'/'.join(x[0] for x in res)
        kind = 'save'
    else:
        raise Exception('unexpected resolution for %s: %r'
                        % (path_msg(name), res))
    # This path must exactly match dest_loc_for_unresolved_path and
    # branch_path_for_vfs_res for equivalent VFS locations (i.e. wrt
    # ==).
    path = b'/'.join(name for name, item in res) or b'/'
    if hasattr(leaf_item, 'coid'):
        result = VFSLoc(type=kind, hash=leaf_item.coid, path=path,
                        vfs_path=vfs_path)
    elif hasattr(leaf_item, 'oid'):
        result = VFSLoc(type=kind, hash=leaf_item.oid, path=path,
                        vfs_path=vfs_path)
    else:
        result = VFSLoc(type=kind, hash=None, path=path, vfs_path=vfs_path)
    return result


Target = namedtuple('Target', ['spec', 'src', 'dest'])

def loc_desc(loc):
    return repr(loc)


def cleanup_vfs_path(p):
    result = os.path.normpath(p)
    if result.startswith(b'/'):
        return result
    return b'/' + result


def adjusted_loc_type_for_vfs_path(kind, path):
    """Return the Loc type (cf. find_vfs_item), kind, adjusted for the
      given (normalized as per cleanup_vfs_path) path.  This does not
      validate the path against the kind (e.g. that a branch doesn't
      end up with 'blob') because it's used in some cases before
      user-friendly validation.  The type mapping is just to handle
      tag vs save/branch dest types.

    """
    # FIXME: test type via some vfs_path_branch_name or similar so
    # we're more insensitive to any future vfs additions (say some new
    # VFS /.* paths)?
    if kind in ('branch', 'save', 'commit'):
        if path.startswith(b'/.tag/'):
            return 'commit'
        return 'branch'
    if kind in ('commit', 'tree', 'blob'):
        return kind
    assert False, f'unexpected type {kind} specified for {path_msg(path)}'


def dest_loc_for_unresolved_path(path, src_kind, spec):
    """Return a normalized, valid VFSLoc for a path that does not yet
    exist.  The src_kind must be a type as per find_vfs_item, and it
    is used to select a suitable destination VFSLoc type.  Since the VFSLoc
    does not exist, it is "unresolved" (no vfs_path).  This does not
    ensure the resulting type is valid for the path.  See
    adjusted_loc_type_for_vfs_path.

    """
    assert path, path # otherwise src.dest would have already been chosen
    path = cleanup_vfs_path(path)
    if path.startswith(b'/.tag/'):
        if not valid_save_name(path[6:]):
            spec_args = spec_msg(spec)
            misuse(f'destination for {spec_args} is not a valid tag name')
    else:
        if path.endswith(b'/'):
            path = path[:-1]
        if not valid_save_name(path[1:]):
            spec_args = spec_msg(spec)
            misuse(f'destination for {spec_args} is not a valid branch name')
    # Now path must exactly match branch_path_for_vfs_res and
    # find_vfs_path for equivalent VFS locations (i.e. wrt ==).
    kind = adjusted_loc_type_for_vfs_path(src_kind, path)
    return VFSLoc(type=kind, hash=None, path=path, vfs_path=None)


def resolve_src(spec, src_repo, *, allow=None):
    assert allow in (None, 'git')
    spec_args = spec_msg(spec)
    if spec.src.startswith(b'git:'):
        if not allow == 'git':
            misuse(f'git references not (yet) allowed here {spec_args}')
        src = find_git_item(spec.src[4:], src_repo)
    else:
        src = find_vfs_item(spec.src, src_repo)
        if src:
            if src.type == 'root':
                misuse('cannot fetch entire repository for %s' % spec_args)
            if src.type == 'tags':
                misuse('cannot fetch entire /.tag directory for %s' % spec_args)
    if not (src or spec.ignore_missing):
        misuse('cannot find source for %s' % spec_args)
    debug1('src: %s\n' % loc_desc(src))
    return src


def branch_path_for_vfs_res(res):
    """Return the vfs path (bytes) for the resolved path, e.g. /branch
    for /branch/SAVE/etc/..."""
    assert len(res) >= 2, res
    assert res[0][0] == b'', res
    assert isinstance(res[0][1], vfs.Root), res
    save_name, save_item = res[1]
    if not save_item:
        misuse(f'error: cannot access {path_msg(save_name)} in {res!r}')
    assert isinstance(save_item, vfs.RevList), res
    # This must exactly match dest_loc_for_unresolved_path and
    # find_vfs_path for equivalent VFS locations (i.e. wrt ==).
    return b'/' + save_name


def resolved_loc_branch_or_tag_path(loc):
    """Return the vfs path (bytes) for the resolved loc,
    e.g. e.g. /branch for /branch/SAVE/etc/..., or /.tag/x/y.

    """
    if isinstance(loc.vfs_path[1][1], vfs.Tags):
        return loc.path
    return branch_path_for_vfs_res(loc.vfs_path)


def resolve_branch_dest(spec, src, dest_repo, dest_changes):
    # Resulting dest must be treeish, or not exist.
    if not spec.dest:
        spec = dcreplace(spec, dest=resolved_loc_branch_or_tag_path(src))
    assert spec.dest, (spec, src)

    dest = dest_changes.get(spec.dest)
    if not dest:
        dest = find_vfs_item(spec.dest, dest_repo)
    if dest:
        if dest.type == 'commit':
            spec_args = spec_msg(spec)
            misuse('destination for %s is a tagged commit, not a branch'
                  % spec_args)
        if dest.type != 'branch':
            spec_args = spec_msg(spec)
            misuse('destination for %s is a %s, not a branch'
                  % (spec_args, dest.type))
    else:
        dest = dest_loc_for_unresolved_path(spec.dest, 'branch', spec)

    # FIXME: tag dest is supposed to be fine (e.g. see --ff in
    # bup-get-(1))?  Assuming so, this should be removed and tests
    # will need adjustment (code above already ensures the path is
    # valid).
    if dest.path.startswith(b'/.'):
        spec_args = spec_msg(spec)
        misuse('destination for %s must be a valid branch name' % spec_args)

    debug1('dest: %s\n' % loc_desc(dest))
    return spec, dest


def resolve_ff(spec, src_repo, dest_repo, dest_changes):
    assert not spec.rewriter, spec
    assert not spec.ignore_missing, spec
    src = resolve_src(spec, src_repo)
    spec_args = spec_msg(spec)
    if src.type == 'tree':
        misuse('%s is impossible; can only --append a tree to a branch'
              % spec_args)
    if src.type not in ('branch', 'save', 'commit'):
        misuse('source for %s must be a branch, save, or commit, not %s'
              % (spec_args, src.type))
    spec, dest = resolve_branch_dest(spec, src, dest_repo, dest_changes)
    return Target(spec=spec, src=src, dest=dest), dcreplace(dest, hash=src.hash)


def handle_ff(item, src_repo, dest_repo):
    assert item.spec.method == 'ff'
    assert item.src.type in ('branch', 'save', 'commit')
    src_oidx = hexlify(item.src.hash)
    if item.dest.hash:
        dest_oidx = hexlify(item.dest.hash)
        if dest_oidx not in src_repo.rev_list(src_oidx):
            misuse('destination is not an ancestor of source for %s'
                   % spec_msg(item.spec))
    # Can fast forward.
    get_random_item(src_oidx, src_repo, dest_repo, item.spec.ignore_missing)
    commit_items = get_commit_items(src_oidx, src_repo.cat)
    return GetResult(item.src.hash, unhexlify(commit_items.tree)), \
        dcreplace(item.dest, hash=item.src.hash)


def resolve_append(spec, src_repo, dest_repo, dest_changes):
    assert not spec.ignore_missing
    src = resolve_src(spec, src_repo)
    if src.type not in ('branch', 'save', 'commit', 'tree'):
        misuse('source for %s must be a branch, save, commit, or tree, not %s'
              % (spec_msg(spec), src.type))
    spec, dest = resolve_branch_dest(spec, src, dest_repo, dest_changes)
    if not spec.rewriter: # hash=None (append is defined to make new commits)
        return Target(spec=spec, src=src, dest=dest), dcreplace(dest, hash=None)

    def vpm(path): return path_msg(b"/".join(x[0] for x in path))
    if not isinstance(src, VFSLoc):
        misuse(f'cannot currently rewrite git location {src}') # GitLoc
    src_path = src.vfs_path
    if len(src_path) != 2: # root, src_ref
        misuse(f'cannot append {vpm(src_path)}')
    src_ref = src_path[1]
    if not isinstance(src_ref[1], vfs.RevList):
        misuse(f'cannot append {vpm(src_path)} saves'
               f' ({path_msg(src_ref[0])} is a {type(src_ref[1])})')
    return Target(spec=spec, src=src, dest=dest), dcreplace(dest, hash=None)


def handle_append(item, src_repo, dest_repo):
    assert item.spec.method == 'append'
    assert item.src.type in ('branch', 'save', 'commit', 'tree')
    assert item.dest.type == 'branch' or not item.dest.type
    parent = item.dest.hash
    if item.src.type == 'tree':
        src_oidx = hexlify(item.src.hash)
        if item.spec.rewriter:
            misuse(f'rewrite cannot yet promote tree to commit for {spec_msg(item.spec)}')
        get_random_item(src_oidx, src_repo, dest_repo, item.spec.ignore_missing)
        msg = commit_message(b'bup get', compat.get_argvb())
        userline = b'%s <%s@%s>' % (userfullname(), username(), hostname())
        now = time.time()
        commit = dest_repo.write_commit(item.src.hash, parent,
                                        userline, now, None,
                                        userline, now, None, msg)
        return GetResult(commit, item.src.hash), \
            dcreplace(item.dest, hash=commit)
    if item.dest.hash:
        assert item.dest.type in ('branch', 'commit', 'save'), item.dest
    res = append_commits(item.src, parent, src_repo, dest_repo,
                         item.spec.rewriter, item.spec.excludes,
                         item.spec.repair_info,
                         item.spec.ignore_missing)
    return res, dcreplace(item.dest, hash=res.oid)


def resolve_pick(spec, src_repo, dest_repo, dest_changes):
    assert not spec.ignore_missing
    src = resolve_src(spec, src_repo)
    spec_args = spec_msg(spec)
    if src.type == 'tree':
        misuse('%s is impossible; can only --append a tree' % spec_args)
    if src.type not in ('commit', 'save'):
        misuse('%s impossible; can only pick a commit or save, not %s'
               % (spec_args, src.type))
    if not spec.dest:
        spec = dcreplace(spec, dest=resolved_loc_branch_or_tag_path(src))
    assert spec.dest, (spec, src)
    if spec.rewriter:
        if src.type != 'save':
            misuse(f'cannot currently --rewrite a {src.type}')

    dest = dest_changes.get(spec.dest)
    if not dest:
        dest = find_vfs_item(spec.dest, dest_repo)
    if not dest:
        dest = dest_loc_for_unresolved_path(spec.dest, 'branch', spec)
        return Target(spec=spec, src=src, dest=dest), dcreplace(dest, hash=None)
    if not dest.type == 'branch' and not dest.path.startswith(b'/.tag/'):
        misuse('%s destination is not a tag or branch' % spec_args)
    if not dest.hash:
        return Target(spec=spec, src=src, dest=dest), dest
    if spec.method != 'force-pick' and dest.path.startswith(b'/.tag/'):
        misuse('cannot overwrite existing tag for %s (requires --force-pick)'
               % spec_args)
    return Target(spec=spec, src=src, dest=dest), dcreplace(dest, hash=None)


def handle_pick(item, src_repo, dest_repo):
    assert item.spec.method in ('pick', 'force-pick')
    assert item.src.type in ('save', 'commit')
    parent = item.dest.hash
    if parent and item.dest.type not in ('branch', 'commit', 'save'):
        assert item.dest.path.startswith(b'/.tag/'), item.dest
        parent = None
    # If there's no parent, either dest is a non-commit tag, we're
    # --force-picking and we should clobber it, or dest doesn't exist.
    res = append_commit(item.src, parent, src_repo, dest_repo,
                        item.spec.rewriter, item.spec.excludes,
                        item.spec.repair_info, item.spec.ignore_missing)
    return res, dcreplace(item.dest, hash=res.oid)


def resolve_new_tag(spec, src_repo, dest_repo, dest_changes):
    assert not spec.rewriter, spec
    assert not spec.ignore_missing, spec
    src = resolve_src(spec, src_repo)
    spec_args = spec_msg(spec)
    if not spec.dest:
        if not src.path.startswith(b'/.tag/'):
            misuse(f'destination for {spec_args} must be a VFS tag')
        spec = dcreplace(spec, dest=src.path)
    assert spec.dest, (spec, src)
    dest = dest_changes.get(spec.dest)
    if not dest:
        dest = find_vfs_item(spec.dest, dest_repo)
    if not dest:
        dest = dest_loc_for_unresolved_path(spec.dest, 'branch', src.type)
    if not dest.path.startswith(b'/.tag/'):
        misuse('destination for %s must be a VFS tag' % spec_args)
    if dest.hash:
        misuse('cannot overwrite existing tag for %s (requires --replace)'
              % spec_args)
    changed_type = adjusted_loc_type_for_vfs_path(src.type, dest.path)
    change = dcreplace(dest, type=changed_type, hash=src.hash)
    return Target(spec=spec, src=src, dest=dest), change


def handle_new_tag(item, src_repo, dest_repo):
    assert item.spec.method == 'new-tag'
    assert item.dest.path.startswith(b'/.tag/')
    get_random_item(hexlify(item.src.hash), src_repo, dest_repo,
                    item.spec.ignore_missing)
    # No rewriting for now, so item.src.hash it is
    return GetResult(item.src.hash), dcreplace(item.dest, hash=item.src.hash)


def resolve_replace(spec, src_repo, dest_repo, dest_changes):
    assert not spec.rewriter, spec
    assert not spec.ignore_missing, spec
    src = resolve_src(spec, src_repo)
    spec_args = spec_msg(spec)
    if not spec.dest:
        if src.type != 'branch' and not src.path.startswith(b'/.tag/'):
            misuse(f'destination for {spec_args} must be a VFS branch or tag')
        spec = dcreplace(spec, dest=src.path)
    assert spec.dest, (spec, src)
    dest = dest_changes.get(spec.dest)
    if not dest:
        dest = find_vfs_item(spec.dest, dest_repo)
    if not dest:
        dest = dest_loc_for_unresolved_path(spec.dest, 'branch', src.type)
    if not dest.type == 'branch' and not dest.path.startswith(b'/.tag/'):
        misuse(f'{spec_args} impossible; can only overwrite branch or tag')
    if not dest.path.startswith(b'/.tag/') \
       and not src.type in ('branch', 'save', 'commit'):
        misuse('cannot overwrite branch with %s for %s' % (src.type, spec_args))
    # Ensure the test is not root or tags or...
    if dest.type != 'branch' and not dest.path.startswith(b'/.tag/'):
        misuse('%s impossible; can only overwrite branch or tag'
               % spec_args)
    changed_type = adjusted_loc_type_for_vfs_path(src.type, dest.path)
    change = dcreplace(dest, type=changed_type, hash=src.hash)
    return Target(spec=spec, src=src, dest=dest), change


def handle_replace(item, src_repo, dest_repo):
    assert item.spec.method == 'replace'
    if item.dest.path.startswith(b'/.tag/'):
        get_random_item(hexlify(item.src.hash), src_repo, dest_repo,
                        item.spec.ignore_missing)
        res = GetResult(item.src.hash)
    else:
        assert item.dest.type == 'branch' or not item.dest.type, item
        src_oidx = hexlify(item.src.hash)
        get_random_item(src_oidx, src_repo, dest_repo, item.spec.ignore_missing)
        commit_items = get_commit_items(src_oidx, src_repo.cat)
        res = GetResult(item.src.hash, unhexlify(commit_items.tree))
    return res, dcreplace(item.dest, hash=item.src.hash)


def resolve_unnamed(spec, src_repo, dest_repo_, dest_changes_):
    assert not spec.rewriter, spec
    if spec.dest:
        misuse('destination name given for %s' % spec_msg(spec))
    src = resolve_src(spec, src_repo, allow='git')
    if src:
        return Target(spec=spec, src=src, dest=None), None
    return None, None


def handle_unnamed(item, src_repo, dest_repo):
    get_random_item(hexlify(item.src.hash), src_repo, dest_repo,
                    item.spec.ignore_missing)
    return GetResult(), None


def resolve_target(spec, src_repo, dest_repo, ref_changes):
    common_args = src_repo, dest_repo, ref_changes
    debug1('initial-spec: %r\n' % (spec,))
    if spec.method == 'ff':
        return resolve_ff(spec, *common_args)
    if spec.method == 'append':
        return resolve_append(spec, *common_args)
    if spec.method in ('pick', 'force-pick'):
        return resolve_pick(spec, *common_args)
    if spec.method == 'new-tag':
        return resolve_new_tag(spec, *common_args)
    if spec.method == 'replace':
        return resolve_replace(spec, *common_args)
    if spec.method == 'unnamed':
        return resolve_unnamed(spec, *common_args)
    # Should be impossible -- prevented by the option parser
    assert False, spec


def git_ref_for_vfs_path(vp):
    # Assumes normalized path (cf cleanup_vfs_path)
    if vp.startswith(b'/.tag/'):
        return b'refs/tags/%s' % vp[6:]
    return b'refs/heads/%s' % vp[1:]


def vfs_path_for_git_ref(ref):
    if ref.startswith(b'refs/heads/'):
        return ref[10:]
    if ref.startswith(b'refs/tags/'):
        return b'/.tag' + ref[9:]
    assert False, ref


def ref_prefixes(ref):
    assert ref, ref
    assert not ref.endswith(b'/'), ref
    assert not ref.startswith(b'/'), ref
    i = ref.find(b'/')
    while i != -1:
        yield ref[:i]
        i = ref.find(b'/', i + 1)


def validate_targets(opt, src_repo, dest_repo):
    resolved_items = []
    ref_changes = {} # vfs_dest_path_bytes -> VFSLoc
    existing_parents = set()
    existing_refs = set()
    for ex_ref, oid_ in dest_repo.refs(limit_to_heads=True, limit_to_tags=True):
        for ex_prefix in ref_prefixes(ex_ref):
            existing_parents.add(ex_prefix)
        existing_refs.add(ex_ref)

    for spec in opt.target_specs:
        res, change = resolve_target(spec, src_repo, dest_repo, ref_changes)
        if not res:
            assert opt.ignore_missing, (spec, opt.ignore_missing)
            assert spec.method == 'unnamed', spec
            assert not change, change
            continue
        resolved_items.append(res)

        if change:
            # Check for attempts to create a ref when the prefix
            # already exists, e.g.:
            #   bup get --ff foo --ff: baz foo/bar
            #   bup get --new-tag .tag/foo --new-tag: bar .tag/foo/bar
            # resolve_METHOD above handles exact overwrites
            ref = git_ref_for_vfs_path(change.path)
            # ensure that ref isn't below an existing ref
            for ref_prefix in ref_prefixes(ref):
                if ref_prefix in existing_refs:
                    vfsp = path_msg(vfs_path_for_git_ref(ref_prefix))
                    refm = path_msg(vfs_path_for_git_ref(ref))
                    misuse(f'{spec_msg(spec)} creates {refm} when {vfsp} exists')
            # ensure that ref isn't above an existing ref
            for ex_parent in existing_parents:
                if ref == ex_parent:
                    vfsp = path_msg(vfs_path_for_git_ref(ex_parent))
                    refm = path_msg(vfs_path_for_git_ref(ref))
                    misuse(f'{spec_msg(spec)} creates {refm} when {vfsp}/ exists')
            for prefix in ref_prefixes(ref):
                existing_parents.add(prefix)
            existing_refs.add(ref)
            ref_changes[change.path] = change
    return resolved_items


def log_method_result(target, result, opt):
    assert isinstance(target, Target), target
    assert isinstance(result, GetResult), result
    dest_path = target.dest and target.dest.path # --unnamed has none
    if dest_path:
        if dest_path.startswith(b'/.tag/'):
            if opt.print_tags: print(result.oid.hex())
        else: # committ
            if opt.print_trees: print(result.tree.hex())
            if opt.print_commits: print(result.oid.hex())
    if opt.verbose:
        name = target.spec.src
        if target.src.type in ('root', 'branch', 'save', 'commit', 'tree') \
           and not name.endswith(b'/'):
            name += b'/'
        if target.spec.method == 'unnamed':
            log(f'{path_msg(name)} -> {target.src.hash.hex()}\n')
        else:
            log(f'{path_msg(name)} -> {result.oid.hex()}\n')


def get_everything(opt):
    repair_count = 0
    with repo_for_url(opt.source_loc) as src_repo, \
         repo_for_location(opt.dst_loc, compression_level=opt.compress) as dest_repo:

        src_split_cfg = hashsplit.configuration(src_repo.config_get)
        dest_split_cfg = hashsplit.configuration(dest_repo.config_get)

        # For now, --rewrite is never implict
        rewrite = False
        for spec in opt.target_specs:
            if spec.rewriter is not None:
                rewrite = True
            elif src_split_cfg != dest_split_cfg:
                misuse('repository configs differ; need --[no-]rewrite before'
                       f' {spec_msg(spec)}')

        # Validate all sources and destinations, implicit or explicit,
        # combinations of methods and modes (rewrite, missing, etc.)
        # and do it up-front, so we can fail before we start writing
        # (for any obviously broken cases).  Do this before creating
        # any database via the Rewriter.
        validate_targets(opt, src_repo, dest_repo)

        # The current arrangement relies on the assumption that any
        # (sub)tree created by a --rewrite is exactly the same tree
        # that --repair would create. If we ever need to change that,
        # then we'll need to drop the relevant dirs from the rewriter
        # (db) when switching from a --rewrite to a
        # --repair. (Regarding the converse, --repairs just never
        # record directory trees in the database.)
        with (Rewriter(split_cfg=dest_split_cfg) if rewrite else nullctx) \
             as rewriter:

            # Until we actually update the refs in the destination
            # repository (after we handle all targets, below), we must
            # *not* rely on the vfs for any new information involving
            # a target's destination ref because targets may change
            # it.  Rely on ref_changes for the current state.  It
            # includes all the info needed for the final update_ref
            # for each modified ref.
            orig_ref_oids = {} # vfs_dest_path_bytes -> oid
            ref_changes = {} # vfs_dest_path_bytes -> VFSLoc

            handlers = {'ff': handle_ff,
                        'append': handle_append,
                        'force-pick': handle_pick,
                        'pick': handle_pick,
                        'new-tag': handle_new_tag,
                        'replace': handle_replace,
                        'unnamed': handle_unnamed}

            def ensure_rewriter(target):
                spec = target.spec
                if not spec.rewriter:
                    return target
                return target._replace(spec=dcreplace(spec, rewriter=rewriter))

            for item in opt.target_specs:
                # The resolve_target ref changes are ignored here
                # because the handlers provide the real information in
                # ref_changes.
                item, ref_change_ = resolve_target(item, src_repo, dest_repo,
                                                   ref_changes)
                if not item:
                    assert opt.ignore_missing, item
                    assert item.spec.method == 'unnamed', item
                    assert not ref_change_, ref_change_
                    continue
                item = ensure_rewriter(item)

                debug1('get-spec: %r\n' % (item.spec,))
                debug1('get-src: %s\n' % loc_desc(item.src))
                debug1('get-dest: %s\n' % loc_desc(item.dest))

                dest_path = item.dest and item.dest.path
                if not item.dest: # e.g. --unnamed doesn't have one
                    cur_item = item
                else:
                    cur_dest = ref_changes.get(dest_path)
                    cur_item = item._replace(dest=cur_dest) if cur_dest \
                        else item

                # item.dest represents the ref's initial state (if
                # any), and cur_dest is the current state, possibly
                # modified by previous targets.
                cur_dest = ref_changes.get(dest_path)
                handler = handlers[item.spec.method]
                get_res, new_dest = handler(cur_item, src_repo, dest_repo)
                repair_count += get_res.repairs

                if dest_path:
                    if dest_path not in ref_changes:
                        orig_ref_oids[dest_path] = item.dest.hash
                    ref_changes[dest_path] = new_dest

                log_method_result(item, get_res, opt)

        # Only update the refs at the very end, once the destination repo
        # finished writing, so that if something goes wrong above, the old
        # refs will be undisturbed.
        for dest_path, new_loc in ref_changes.items():
            dest_ref = git_ref_for_vfs_path(dest_path)
            orig_oid = orig_ref_oids[dest_path]
            try:
                dest_repo.update_ref(dest_ref, new_loc.hash, orig_oid)
                if opt.verbose:
                    new_hex = hexlify(new_loc.hash).decode('ascii')
                    ref_msg = path_msg(dest_ref)
                    if orig_oid:
                        orig_hex = hexlify(orig_oid).decode('ascii')
                        log(f'updated {ref_msg} ({orig_hex} -> {new_hex})\n')
                    else:
                        log(f'updated {ref_msg} ({new_hex})\n')
            except (git.GitError, client.ClientError) as ex:
                note_error('unable to update ref %r: %s\n' % (dest_ref, ex))

    if repair_count and not saved_errors:
        msg = ('Repairs were needed and successful; see above. Additional'
               ' information may be found in the git log. Search for'
               ' "Repair-ID:" in "git --git-dir REPO log ..." for the related'
               ' references.\n')
        log(f'\n{fill(msg, width=tty_width(), break_on_hyphens=False)}\n')
        return EXIT_RECOVERED
    return 0

def main(argv):
    opt = parse_args(argv)
    git.check_repo_or_die()
    if opt.bwlimit:
        client.bwlimit = opt.bwlimit
    return get_everything(opt)
