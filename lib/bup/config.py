
from bup.io import path_msg as pm
from bup.url import URL, parse_bytes_path_url


class ConfigError(Exception):
    pass


def url_for_remote_opt(remote):
    """Return a URL for a remote (e.g. --remote) value.  Return a
    descriptive string for invalid values."""
    def parse_non_url(remote):
        user, at_, hostpath = remote.rpartition(b'@') # ssh x@y@z has user x@y
        if b':' not in hostpath:
            return f'remote {pm(remote)} has no colon'
        host, path = hostpath.split(b':', 1)
        if host == b'-': # use a subprocess for testing
            return URL(scheme=b'ssh', path=path)
        if not host:
            return f'remote {pm(remote)} has no host'
        return URL(scheme=b'ssh', host=host, user=user, path=path)
    url = parse_bytes_path_url(remote, require_auth=True)
    if isinstance(url, (str, type(None))):
        return parse_non_url(remote)
    if url.scheme == b'bup':
        if url.user:
            return f'bup URL {pm(remote)} has a user'
    elif url.scheme in (b'ssh', b'bup'): # for now
        if not url.host: # i.e. b''
            return f'remote {pm(remote)} has no host'
    elif url.scheme == b'bup-rev':
        if url.user: return f'bup-rev remote {pm(remote)} has a user'
        if url.path: return f'bup-rev remote {pm(remote)} has a path'
        if url.port is not None: return f'bup-rev remote {pm(remote)} has a port'
    else:
        return f'unexpected remote scheme {pm(url.scheme)} in {pm(remote)}'
    return url
