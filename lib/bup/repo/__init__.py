
from bup.repo import local, remote


LocalRepo = local.LocalRepo
RemoteRepo = remote.RemoteRepo

def make_repo(address, create=False, compression_level=None,
              max_pack_size=None, max_pack_objects=None):
    opts = {'compression_level': compression_level,
            'max_pack_objects': max_pack_objects,
            'max_pack_size': max_pack_size}
    if address.startswith(b'file://'):
        path = address[len(b'file://'):]
        if create:
            LocalRepo.create(path)
        return LocalRepo(repo_dir=path, **opts)
    if address.startswith(b'bup+ssh://'):
        address = address[len(b'bup+ssh://'):]
    elif not address.startswith(b'bup-rev://'):
        raise Exception(f'unrecognized repository address {address}')
    return RemoteRepo(address, create=create, **opts)
