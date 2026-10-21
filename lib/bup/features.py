
from platform import python_version_tuple

from bup import _helpers, metadata
from bup.version import version as bup_version


def skeleton():
    # For use instead of None as "no info" to make provision checks
    # easier.  Whenever 'version' exists, the info is real.
    return {'provides': []}

def validate(info):
    # Enforce minimal requirements
    if not isinstance(info, dict) \
       or not 'provides' in info \
       or not all(isinstance(x, str) for x in info['provides']):
        raise ValueError(f'Invalid client info: {info!r}')
    return info

def get():
    provides = []
    if getattr(_helpers, 'read_acl', None):
        provides.append('posix1e-acls')
    if metadata.xattr:
        provides.append('linux-xattrs')
    if getattr(_helpers, 'readline', None):
        provides.append('readline')
    provides.sort()
    # This must be vint tree compatible
    return {'version': bup_version.decode('utf-8'),
            'python': python_version_tuple(),
            'provides': provides}
