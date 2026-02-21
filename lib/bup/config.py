
from os import environb as environ
from urllib.parse import quote_from_bytes

import bup.path


class ConfigError(Exception):
    pass


def derive_repo_addr(*, remote, die):
    # Note: remote is -r argument
    reverse = environ.get(b'BUP_SERVER_REVERSE')
    if remote:
        if reverse:
            die("don't use -r in reverse mode; it's automatic")
        return b'ssh://' + remote
    if reverse:
        # Since it should effectively always be a hostname provided by
        # on--server, make it the URL host.
        return b'bup-rev://' + quote_from_bytes(reverse, safe='').encode('ascii')
    return b'file://' + bup.path.defaultrepo()
