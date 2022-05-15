
from __future__ import absolute_import, print_function
import platform, sys

from bup import _helpers, metadata, options, version
from bup.io import byte_stream

out = None

def show_support(out, bool_opt, what):
    out.write(b'    %s: %s\n' % (what, b'yes' if bool_opt else b'no'))

optspec = """
bup features
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])

    sys.stdout.flush()
    out = byte_stream(sys.stdout)

    out.write(b'bup %s\n' % version.version)
    out.write(b'Source %s %s\n' % (version.commit, version.date))

    have_readline = getattr(_helpers, 'readline', None)
    have_libacl = getattr(_helpers, 'read_acl', None)
    have_xattr = metadata.xattr

    out.write(b'    Python: %s\n' % platform.python_version().encode('ascii'))
    show_support(out, have_readline, b'Command line editing (e.g. bup ftp)')
    show_support(out, have_libacl, b'Saving and restoring POSIX ACLs')
    show_support(out, have_xattr, b'Saving and restoring extended attributes (xattrs)')
