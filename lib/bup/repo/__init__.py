
from bup.repo import local, remote


LocalRepo = local.LocalRepo
RemoteRepo = remote.RemoteRepo

def make_repo(address, create=False, compression_level=None,
              max_pack_size=None, max_pack_objects=None):
    return RemoteRepo(address, create=create,
                      compression_level=compression_level,
                      max_pack_size=max_pack_size,
                      max_pack_objects=max_pack_objects)
