
from os import environb as environ
from typing import Callable, NoReturn

from bup import client
from bup.compat import argv_bytes
from bup.config import url_for_remote_opt
from bup.path import defaultrepo
from bup.repo import local, remote
from bup.url import URL


LocalRepo = local.LocalRepo
RemoteRepo = remote.RemoteRepo


def repo_location_url(location):
    if isinstance(location, URL):
        return location
    if isinstance(location, client.Config):
        return location.url
    raise Exception(f'unexpected location type {location}')


def main_repo_location(remote, die: Callable[[str], NoReturn]):
    """Return a repository location for a typical command.

    Return bup-rev URL if BUP_SERVER_REVERSE if set, a
    bup.client.Config for the remote (--remote) if any, or finally, a
    file URL for the default repository (e.g. BUP_DIR); die if both
    reverse and remote are requested, or if the remote is
    unrecognizable.

    """
    # pylint (3.3.4) ignores die NoReturn annotation
    def die_(msg) -> NoReturn: die(msg)
    reverse = environ.get(b'BUP_SERVER_REVERSE')
    if reverse:
        if remote:
            die_("don't use -r in reverse mode; it's automatic")
        return URL(scheme=b'bup-rev', host=reverse)
    if not remote:
        return URL(scheme=b'file', path=defaultrepo())
    url = url_for_remote_opt(remote)
    if isinstance(url, str):
        die_(url)
    return client.Config(remote=remote, url=url)


def repo_for_url(url, **kwargs):
    if url.scheme == b'file':
        if kwargs.pop('create', None):
            LocalRepo.create(url.path)
        return LocalRepo(repo_dir=url.path, **kwargs)
    if url.scheme in (b'ssh', b'bup', b'bup-rev'):
        return RemoteRepo(url, **kwargs)
    raise Exception(f'unrecognized repository URL {url}')


def repo_for_location(location, **kwargs):
    if isinstance(location, URL):
        return repo_for_url(location, **kwargs)
    if isinstance(location, client.Config):
        return RemoteRepo(location, **kwargs)
    raise Exception(f'unexpected repository location {location}')
