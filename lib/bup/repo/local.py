
import os, subprocess
from os import path
from os.path import realpath
from functools import partial

from bup import git, vfs
from bup.config import ConfigError
from bup.git import LocalPackStore, PackWriter
from bup.repo.base import _make_base, RepoProtocol


class LocalRepo(RepoProtocol):
    def __init__(self, repo_dir=None, compression_level=None,
                 max_pack_size=None, max_pack_objects=None,
                 allow_duplicates=None, server=False, run_midx=None,
                 on_pack_finish=None):
        """When allow_duplicates is false, (at some cost) avoid
        writing duplicates of objects that already in the repository.

        """
        # allow_duplicates instead of deduplicate_writes so None can
        # indicate unset without being conflated with False.
        self.closed = True
        self.repo_dir = realpath(repo_dir or git.guess_repo())
        self._base = _make_base(self.config_get, compression_level,
                                max_pack_size, max_pack_objects)
        self._on_pack_finish = on_pack_finish
        self._packwriter = None
        self.write_symlink = self.write_data
        self.write_bupm = self.write_data
        self._cp = git.cp(self.repo_dir)
        self.rev_list = partial(git.rev_list, repo_dir=self.repo_dir)

        if server:
            # Ensure srv_dedup and allow_duplicates agree if server is true
            srv_dedup = self.config_get(b'bup.server.deduplicate-writes', opttype='bool')
            if srv_dedup is not None and allow_duplicates is not None \
               and bool(srv_dedup) == bool(allow_duplicates):
                raise ValueError(f'conflicting allow_duplicates ({allow_duplicates!r})'
                                 f' and bup.server.deduplicate-writes ({srv_dedup!r})')
        if server and srv_dedup == False:
            assert not allow_duplicates
            # don't make midx files
            assert run_midx is None
            self.run_midx = False
            self._deduplicate_writes = False
        else: # srv_dedup is true or unset
            self.run_midx = True if run_midx is None else run_midx
            if allow_duplicates:
                self._deduplicate_writes = False
            else:
                self._deduplicate_writes = True
        self.closed = False

    def close(self):
        if not self.closed:
            self.closed = True
            self.finish_writing()

    def __del__(self): assert self.closed
    def __enter__(self): return self
    def __exit__(self, type, value, traceback): self.close()

    def is_remote(self): return False

    @classmethod
    def create(self, repo_dir=None):
        # FIXME: this is not ideal, we should somehow
        # be able to call the constructor instead?
        git.init_repo(repo_dir)

    def config_get(self, name, *, opttype=None):
        cfg = git.git_config_get(git.repo_config_file(self.repo_dir),
                                 name, opttype=opttype)
        if name != b'bup.server.deduplicate-writes':
            return cfg
        assert opttype == 'bool'
        if path.exists(git.repo(b'bup-dumb-server', repo_dir=self.repo_dir)):
            if not cfg: # whether None or False
                return False
            raise ConfigError('bup-dumb-server exists and bup.server.deduplicate-writes is true')
        return cfg

    def list_indexes(self):
        yield from os.listdir(git.repo(b'objects/pack', repo_dir=self.repo_dir))

    def read_ref(self, refname):
        return git.read_ref(refname, repo_dir=self.repo_dir)

    def _ensure_packwriter(self):
        if not self._packwriter:
            store = LocalPackStore(repo_dir=self.repo_dir,
                                   on_pack_finish=self._on_pack_finish,
                                   run_midx=self.run_midx)
            writer = PackWriter(store=store,
                                compression_level=self._base.compression_level,
                                max_pack_size=self._base.max_pack_size,
                                max_pack_objects=self._base.max_pack_objects)
            self._packwriter = writer

    def update_ref(self, refname, newval, oldval):
        self.finish_writing()
        return git.update_ref(refname, newval, oldval, repo_dir=self.repo_dir)

    def cat(self, ref):
        it = self._cp.get(ref)
        oidx, typ, size = info = next(it)
        yield info
        if oidx: yield from it
        assert not next(it, None)

    def join(self, ref):
        return vfs.join(self, ref)

    def resolve(self, path, parent=None, want_meta=True, follow=True):
        ## FIXME: mode_only=?
        return vfs.resolve(self, path, parent=parent,
                           want_meta=want_meta, follow=follow)

    def refs(self, patterns=None, limit_to_heads=False, limit_to_tags=False):
        yield from git.list_refs(patterns=patterns,
                                 limit_to_heads=limit_to_heads,
                                 limit_to_tags=limit_to_tags,
                                 repo_dir=self.repo_dir)

    def send_index(self, name, conn, send_size):
        with git.open_idx(git.repo(b'objects/pack/%s' % name,
                                   repo_dir=self.repo_dir)) as idx:
            send_size(len(idx.map))
            conn.write(idx.map)

    def rev_list_raw(self, refs, fmt):
        """
        Yield chunks of data of the raw rev-list in git format.
        (optional, used only by bup server)
        """
        args = git.rev_list_invocation(refs, format=fmt)
        p = subprocess.Popen(args, env=git._gitenv(self.repo_dir),
                             stdout=subprocess.PIPE)
        while True:
            out = p.stdout.read(64 * 1024)
            if not out:
                break
            yield out
        rv = p.wait()  # not fatal
        if rv:
            raise git.GitError('git rev-list returned error %d' % rv)

    def write_commit(self, tree, parent,
                     author, adate_sec, adate_tz,
                     committer, cdate_sec, cdate_tz,
                     msg):
        self._ensure_packwriter()
        return self._packwriter.new_commit(tree, parent,
                                           author, adate_sec, adate_tz,
                                           committer, cdate_sec, cdate_tz,
                                           msg)

    def write_tree(self, shalist):
        self._ensure_packwriter()
        return self._packwriter.new_tree(shalist)

    def write_data(self, data):
        self._ensure_packwriter()
        return self._packwriter.new_blob(data)

    def just_write(self, sha, type, content):
        self._ensure_packwriter()
        return self._packwriter.just_write(sha, type, content)

    def exists(self, sha, want_source=False):
        self._ensure_packwriter()
        return self._packwriter.exists(sha, want_source=want_source)

    def finish_writing(self):
        if self._packwriter:
            w = self._packwriter
            self._packwriter = None
            return w.close()
        return None

    def abort_writing(self):
        if self._packwriter:
            self._packwriter.abort()
