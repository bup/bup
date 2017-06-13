
from bup import client, git


class LocalRepo:
    def __init__(self, repo_dir=None):
        self.repo_dir = repo_dir or git.repo()
        self._cp = git.cp(repo_dir)

    def join(self, ref):
        return self._cp.join(ref)

class RemoteRepo:
    def __init__(self, address):
        self.address = address
        self.client = client.Client(address)

    def join(self, ref):
        return self.client.cat(ref)
