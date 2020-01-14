
from __future__ import absolute_import

from bup.repo import local, remote


LocalRepo = local.LocalRepo
RemoteRepo = remote.RemoteRepo

def make_repo(address, create=False):
    return RemoteRepo(address, create=create)
