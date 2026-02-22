
from os import devnull, environb as environ, fsencode

import pytest

from bup.client import Config
from bup.repo import repo_location_url, main_repo_location
from bup.url import URL


def test_location_url():
    url = URL(scheme=b'ssh')
    assert repo_location_url(url) is url
    assert repo_location_url(Config(remote=b'h:x', url=url)) is url


def test_main_repo_location():
    class Died(Exception): pass
    def die(msg): raise Died(msg)
    def file(**kwargs): return URL(scheme=b'file', **kwargs)
    def ssh(**kwargs): return URL(scheme=b'ssh', **kwargs)
    def config(reverse, remote):
        orig_rev = environ.get(b'BUP_SERVER_REVERSE', None)
        try:
            if reverse is not None:
                environ[b'BUP_SERVER_REVERSE'] = reverse
            return main_repo_location(remote, die)
        finally:
            if orig_rev is None:
                environ.pop(b'BUP_SERVER_REVERSE', None)
            else:
                environ[b'BUP_SERVER_REVERSE'] = orig_rev

    assert config(None, None) == file(path=fsencode(devnull)) # conftest.py
    assert config(None, b'h:x') == Config(remote=b'h:x',
                                          url=ssh(host=b'h', path=b'x'))
    with pytest.raises(Exception, match='has no colon'):
        config(None, b'-')
    assert config(b'r', None) == URL(scheme=b'bup-rev', host=b'r')
