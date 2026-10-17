
from platform import python_version_tuple

from bup import _helpers, metadata
from bup.version import version as bup_version


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
