
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Optional, Union
from urllib.parse import unquote_to_bytes
import re

from bup.compat import dataclass
from bup.io import path_msg as pm

## Current schemes

# As an extension, some schemes (file, ssh) support having a path with
# a leading "/./" to indicate a relative path for a URL with an
# authority (ie. one that starts with scheme://).  For example, for a
# dot-encoded scheme, scheme:foo, scheme://host/./foo, and
# scheme:///./foo all specify the relative path foo.  Note that
# dot-encoding only appears in rendered URL strings, not a URL
# instance's path.

def dot_encode_path(path):
    if path and not path.startswith(b'/'):
        return b'/./' + path
    return path

@dataclass(slots=True, frozen=True)
class URL:
    # This allows invalid (relative) paths (e.g. when there's also an
    # authority), expecting that they'll be handled elsewhere (for
    # example during serialization, perhaps via dot-encoding).
    scheme: bytes
    host: Union[IPv4Address, IPv6Address, bytes] = b''
    port: Optional[int] = None
    user: bytes = b''
    path: bytes = b''
    def _has_auth(self):
        return self.port is not None or self.host or self.user
    def __post_init__(self):
        assert self.scheme, self.scheme
        assert isinstance(self.host, (IPv4Address, IPv6Address, bytes)), self.host
        assert isinstance(self.port, (int, type(None))), self.port
        assert isinstance(self.user, bytes), self.user
        assert isinstance(self.path, bytes), self.path

# Needs percent encoding (inverted _host_reg_name_rx below without %)
_enc_host_char_rx = re.compile(br"[^-._~0-9a-zA-Z!$&'()*+,;=']")
# Same as above plus colon
_enc_userinfo_char_rx = re.compile(br"[^-._~0-9a-zA-Z!$&'()*+,;=':]")

def _pct_encode(x, rx):
    def enc(m):
        c = m.group(0)
        assert len(c) == 1
        return b'%%%02x' % c[0]
    return rx.sub(enc, x)

def render_url(self, dot_encode=False):
    """Render a url as bytes, e.g. b'ssh://u@h/p'.  When dot_encode is
    true, dot encode the path when necessary, otherwise throw a
    ValueError.

    """
    def with_auth(path):
        assert self.scheme, self
        parts = [self.scheme, b'://']
        if self.user:
            parts.append(_pct_encode(self.user, _enc_userinfo_char_rx))
            parts.append(b'@')
        if self.host:
            if isinstance(self.host, IPv4Address):
                parts.append(self.host.compressed.encode('ascii'))
            elif isinstance(self.host, IPv6Address):
                parts.append(f'[{self.host.compressed}]'.encode('ascii'))
            else:
                parts.append(_pct_encode(self.host, _enc_host_char_rx))
        if self.port:
            parts.append(b':%d' % self.port)
        parts.append(path)
        return b''.join(parts)
    if self._has_auth():
        if not self.path.startswith(b'/'):
            if dot_encode:
                return with_auth(dot_encode_path(self.path))
            if self.path:
                raise ValueError('URL with authority cannot represent relative path'
                                 f' {pm(self.path)}')
        return with_auth(self.path)
    if self.path.startswith(b'//'):
        return with_auth(self.path)
    return b'%s:%s' % (self.scheme, self.path)

_scheme_and_rest_rx = re.compile(br'([a-zA-Z][-+.a-zA-Z0-9]*):(//)?(.*)')
_userinfo_host_port_rx = re.compile(br"(?:([-._~0-9a-zA-Z!$&'()*+,;='%:]*)@)?(.*?)(?::([0-9]*))?")
#                                      ^------------- user ----------------^      ^--- port --^
_host_reg_name_rx = re.compile(br"[-._~0-9a-zA-Z!$&'()*+,;='%]*")
_port_int_rx = re.compile(br'[0-9]+')

class ParseError(Exception): pass

def parse_bytes_path_url(url, require_auth=False):
    """Parse URL mostly according to RFC 3986.  Return None if it
    doesn't appear to be a URL at all (or doesn't start with a scheme
    and authority when require_auth is true).  Return a string
    summarizing what's wrong if part of the URL is invalid
    (e.g. "invalid host 'foo\xb5'").  Return a URL instance on
    success.

    Return the URL's path bytes without any interpretation or decoding
    so that this function is suitable for URL-like references
    referring to filesystem paths provided via the command line.
    Parse the rest of the URL mostly according to the RFC, including
    percent decoding the host and user.

    RFC 3986 Uniform Resource Identifier (URI): Generic Syntax
    https://datatracker.ietf.org/doc/html/rfc3986

    """
    def parse_addr(addr):
        try:
            return ip_address(addr.decode('ascii'))
        except ValueError:
            return None
    m = _scheme_and_rest_rx.fullmatch(url)
    if not m:
        return None
    scheme, slashes, rest = m.group(1, 2, 3)
    if not slashes: # no authority (not even an empty one) x:... not x://...
        if require_auth:
            return None
        return URL(scheme=scheme, path=rest)
    auth, slash, path = rest.partition(b'/')
    if slash: path = b'/' + path
    if not auth: # Use a subprocess for testing
        return URL(scheme=scheme, path=path)
    m = _userinfo_host_port_rx.fullmatch(auth)
    assert m, url # we know auth is not empty, and rx has .*
    user, host, port = m.groups(b'')
    # drop the password immediately (RFC concurs)
    user, colon_, passwd_ = user.partition(b':')
    user = unquote_to_bytes(user)
    port = int(port) if port else None
    # REVIEW: is ip_address exactly right for this?
    if host and host[0] == b'['[0] and host[-1] == b']'[0]:
        addr = parse_addr(host[1:-1])
        if isinstance(addr, IPv6Address):
            return URL(scheme=scheme, host=addr, port=port, user=user, path=path)
    addr = parse_addr(host)
    if isinstance(addr, IPv4Address):
        return URL(scheme=scheme, host=addr, port=port, user=user, path=path)
    if not _host_reg_name_rx.fullmatch(host):
        return f'invalid host {pm(host)}'
    host = unquote_to_bytes(host)
    return URL(scheme=scheme, host=host, port=port, user=user, path=path)
