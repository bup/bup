
from os import environb as environ

import bup.path


class ConfigError(Exception):
    pass


def derive_repo_addr(*, remote, die):
    # Note: remote is -r argument
    reverse = environ.get(b'BUP_SERVER_REVERSE')
    if remote:
        if reverse:
            die("don't use -r in reverse mode; it's automatic")
        return b'bup+ssh://' + remote
    if reverse:
        return (b'bup-rev://' + reverse)
    return b'file://' + bup.path.defaultrepo()
