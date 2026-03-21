
from ipaddress import IPv4Address, IPv6Address

from pytest import raises

from bup.url import URL, render_url
import bup.url


def test_dot_encode_path():
    enc = bup.url.dot_encode_path
    assert enc(b'') == b''
    assert enc(b'x') == b'/./x'
    assert enc(b'/x') == b'/x'

ip4 = IPv4Address
ip6 = IPv6Address
# Cases that can round-trip through parse/render, i.e. those that
# don't require dot-encoding or don't have more than one serialized
# form (e.g. x: and x:// or x:/ and x:///).  We do include one of each
# of the ambiguous cases, i.e. the one that render_url produces.
symmetric_cases = \
    ((b'x:', URL(scheme=b'x')),
     (b'x:/', URL(scheme=b'x', path=b'/')),
     (b'x:/p', URL(scheme=b'x', path=b'/p')),
     (b'x:/\xb5', URL(scheme=b'x', path=b'/\xb5')),
     (b'x:', URL(scheme=b'x')),
     (b'x:p', URL(scheme=b'x', path=b'p')),
     (b'x://h', URL(scheme=b'x', host=b'h')),
     (b'x://192.168.1.1', URL(scheme=b'x', host=ip4('192.168.1.1'))),
     (b'x://[::]', URL(scheme=b'x', host=ip6('::'))),
     (b'x://[ff::1]', URL(scheme=b'x', host=ip6('ff::1'))),
     (b'x://-', URL(scheme=b'x', host=b'-')),
     (b'x://h/', URL(scheme=b'x', host=b'h', path=b'/')),
     (b'x://-/', URL(scheme=b'x', host=b'-', path=b'/')),
     (b'x://:1', URL(scheme=b'x', port=1)),
     (b'x://p:1', URL(scheme=b'x', host=b'p', port=1)),
     (b'x://p:1/', URL(scheme=b'x', host=b'p', port=1, path=b'/')),
     (b'x://u@/', URL(scheme=b'x', user=b'u', path=b'/')),
     (b'x://u@h:1', URL(scheme=b'x', host=b'h', port=1, user=b'u')),
     (b'x://u@h:1/', URL(scheme=b'x', host=b'h', port=1, user=b'u', path=b'/')),
     (b'x://u@h:1/p', URL(scheme=b'x', host=b'h', port=1, user=b'u', path=b'/p')))

# FIXME: more negative tests
def test_render_url():
    def urlx(**kwargs): return URL(scheme=b'x', **kwargs)
    def rdot(url): return render_url(url, dot_encode=True)
    rurl = render_url
    for rendered, url in symmetric_cases:
        assert render_url(url) == rendered

    with raises(ValueError, match='cannot represent relative path'):
        rurl(urlx(host=b'h', path=b'p'))
    assert rurl(urlx(path=b'//p')) == b'x:////p'
    assert rurl(urlx(host=b'%')) == b'x://%25'
    assert rurl(urlx(host=b':', user=b'/')) == b'x://%2f@%3a'
    assert rdot(urlx(host=b'h', path=b'p')) == b'x://h/./p'

# FIXME: more negative tests
def test_parse_bytes_path_url():
    parse = bup.url.parse_bytes_path_url

    assert parse(b'x:', require_auth=True) is None
    assert parse(b'x:/', require_auth=True) is None
    assert parse(b'x://', require_auth=True) == URL(scheme=b'x')
    assert parse(b':') is None
    assert parse(b':y') is None
    assert parse(b'-') is None
    assert parse(b'-:') is None
    assert parse(b'x://h:x') == 'invalid host h:x'

    # Test the second rendered form for URLs with two options (other
    # is in semetric_cases above).
    assert parse(b'x://') == URL(scheme=b'x') # i.e. x:
    assert parse(b'x:///') == URL(scheme=b'x', path=b'/') # i.e. x:/
    assert parse(b'x:///p') == URL(scheme=b'x', path=b'/p') # i.e. x:/p
    assert parse(b'x://:') == URL(scheme=b'x') # i.e. x:
    assert parse(b'x://:/') == URL(scheme=b'x', path=b'/') # i.e. x:/
    assert parse(b'x://@/') == URL(scheme=b'x', path=b'/') # i.e. x:/
    assert parse(b'x://@:/') == URL(scheme=b'x', path=b'/') # i.e. x:/
    assert parse(b'x://@h/') == URL(scheme=b'x', host=b'h', path=b'/') # i.e. x://h/
    assert parse(b'x://%75@h:1') == URL(scheme=b'x', host=b'h', port=1, user=b'u') # i.e. x://u@h:1
    assert parse(b'x://%75@h:1/') == URL(scheme=b'x', host=b'h', port=1, user=b'u', path=b'/') # i.e. x://u@h:1
    assert parse(b'x://u@%68:1') == URL(scheme=b'x', host=b'h', port=1, user=b'u') # i.e. x://u@h:1
    assert parse(b'x://u@%68:1/') == URL(scheme=b'x', host=b'h', port=1, user=b'u', path=b'/') # i.e. x://u@h:1/
    assert parse(b'x://u@%68:1/p') == URL(scheme=b'x', host=b'h', port=1, user=b'u', path=b'/p') # i.e. x://u@h:1/p
    assert parse(b'ssh://u@%68:1/p') == URL(scheme=b'ssh', host=b'h', port=1, user=b'u', path=b'/p')

    for rendered, url in symmetric_cases:
        assert parse(rendered) == url
