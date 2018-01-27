
from __future__ import absolute_import
from functools import partial

from bup import client, git


class LocalRepo:
    def __init__(self, repo_dir=None):
        self.repo_dir = repo_dir or git.repo()
        self._cp = git.cp(repo_dir)
        self.rev_list = partial(git.rev_list, repo_dir=repo_dir)

    def cat(self, ref):
        """If ref does not exist, yield (None, None, None).  Otherwise yield
        (oidx, type, size), and then all of the data associated with
        ref.

        """
        it = self._cp.get(ref)
        oidx, typ, size = info = next(it)
        yield info
        if oidx:
            for data in it:
                yield data
        assert not next(it, None)

    def join(self, ref):
        return self._cp.join(ref)

    def refs(self, patterns=None, limit_to_heads=False, limit_to_tags=False):
        for ref in git.list_refs(patterns=patterns,
                                 limit_to_heads=limit_to_heads,
                                 limit_to_tags=limit_to_tags,
                                 repo_dir=self.repo_dir):
            yield ref

class RemoteRepo:
    def __init__(self, address):
        self.address = address
        self.client = client.Client(address)
        self.rev_list = self.client.rev_list

    def cat(self, ref):
        """If ref does not exist, yield (None, None, None).  Otherwise yield
        (oidx, type, size), and then all of the data associated with
        ref.

        """
        # Yield all the data here so that we don't finish the
        # cat_batch iterator (triggering its cleanup) until all of the
        # data has been read.  Otherwise we'd be out of sync with the
        # server.
        items = self.client.cat_batch((ref,))
        oidx, typ, size, it = info = next(items)
        yield info[:-1]
        if oidx:
            for data in it:
                yield data
        assert not next(items, None)

    def join(self, ref):
        return self.client.join(ref)

    def refs(self, patterns=None, limit_to_heads=False, limit_to_tags=False):
        for ref in self.client.refs(patterns=patterns,
                                    limit_to_heads=limit_to_heads,
                                    limit_to_tags=limit_to_tags):
            yield ref
