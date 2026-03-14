
from ipaddress import IPv4Address, IPv6Address

from bup import config
from bup.url import URL


def test_url_for_remote_opt():
    def ssh(**kwargs): return URL(scheme=b'ssh', **kwargs)
    def bup(**kwargs): return URL(scheme=b'bup', **kwargs)
    def bup_rev(**kwargs): return URL(scheme=b'bup-rev', **kwargs)
    ip4 = IPv4Address
    ip6 = IPv6Address
    def parse(remote): return config.url_for_remote_opt(remote)

    assert parse(b':') == 'remote : has no host'
    assert parse(b':x') == 'remote :x has no host'
    assert parse(b'x:') == ssh(host=b'x')
    assert parse(b'x:y') == ssh(host=b'x', path=b'y')
    assert parse(b'x:y:z') == ssh(host=b'x', path=b'y:z')
    assert parse(b'u@x:') == ssh(host=b'x', user=b'u')
    assert parse(b'u@u@x:') == ssh(host=b'x', user=b'u@u')
    assert parse(b'u@x:/') == ssh(host=b'x', user=b'u', path=b'/')
    assert parse(b'w:x@y:z') == ssh(host=b'y', user=b'w:x', path=b'z')
    assert parse(b'-:/bup') == ssh(path=b'/bup')
    assert parse(b'192.168.1.1:/bup') == ssh(host=b'192.168.1.1', path=b'/bup')
    assert parse(b'ssh://192.168.1.1:2222/bup') == ssh(host=ip4('192.168.1.1'), port=2222, path=b'/bup')
    assert parse(b'ssh://[ff:fe::1]:2222/bup') == ssh(host=ip6('ff:fe::1'), port=2222, path=b'/bup')
    assert parse(b'bup://foo.com:1950') ==  bup(host=b'foo.com', port=1950)
    assert parse(b'bup://foo.com:1950/bup') == bup(host=b'foo.com', port=1950, path=b'/bup')
    assert parse(b'bup://[ff:fe::1]/bup') == bup(host=ip6('ff:fe::1'), path=b'/bup')
    assert parse(b'bup://[ff:fe::1]/bup') == bup(host=ip6('ff:fe::1'), path=b'/bup')
    assert parse(b'bup-rev://%2f') == bup_rev(host=b'/')
    assert 'has a port' in parse(b'bup-rev://:1')
    assert 'has a user' in parse(b'bup-rev://u@')
    assert 'has a path' in parse(b'bup-rev:///dir')
    assert parse(b'http://asdf.com/bup') == \
        'unexpected remote scheme http in http://asdf.com/bup'
