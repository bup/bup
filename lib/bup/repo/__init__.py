
from os import environb as environ
from typing import Callable, NoReturn

from bup import client
from bup.compat import argv_bytes
from bup.config import url_for_remote_opt
from bup.io import path_msg as pm
from bup.path import defaultrepo
from bup.repo.local import LocalRepo
from bup.repo.remote import RemoteRepo
from bup.url import URL, parse_bytes_path_url


public_schemes = frozenset([b'file', b'ssh', b'bup'])


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


def parse_repo_url_arg(arg, val, misuse):
    """Call misuse(err_msg) if val is not a valid URL, otherwise
    return a corresponding URL instance."""
    url = parse_bytes_path_url(val)
    if not url:
        misuse(f'invalid {arg} {pm(val)}')
    if isinstance(url, str):
        misuse(f'invalid {arg} {pm(val)} ({url})')
    url = repo_location_url(url)
    if url.scheme not in public_schemes:
        misuse(f'invalid {arg} schema in {pm(val)}')
    if url.scheme == b'file' and url.auth:
        misuse(f'{arg} {pm(val)} URL has extra leading slashes or an authority')
    return url
