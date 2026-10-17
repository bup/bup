
import platform, sys

from bup import features, options, version
from bup.helpers import EXIT_FALSE, EXIT_SUCCESS, EXIT_TRUE
from bup.io import byte_stream


def show_support(out, bool_opt, what):
    out.write(b'    %s: %s\n' % (what, b'yes' if bool_opt else b'no'))

optspec = """
bup features
--
provides=  exit 0 if all of the provisions are available, or 1
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    if extra:
        o.fatal('expected no arguments')

    provides = features.get()['provides']

    if opt.provides:
        everything = True
        for arg, val in flags:
            if arg == '--provides':
                if val not in provides:
                    everything = False
            else:
                o.fatal(f'argument incompatible with --provides: {arg}')
        return EXIT_TRUE if everything else EXIT_FALSE

    sys.stdout.flush()
    out = byte_stream(sys.stdout)

    out.write(b'bup %s\n' % version.version)
    out.write(b'Source %s %s\n' % (version.commit, version.date))

    have_readline = 'readline' in provides
    have_libacl = 'posix1e-acls' in provides
    have_xattr = 'linux-xattrs' in provides

    out.write(b'    Python: %s\n' % platform.python_version().encode('ascii'))
    show_support(out, have_readline, b'Command line editing (e.g. bup ftp)')
    show_support(out, have_libacl, b'Saving and restoring POSIX ACLs')
    show_support(out, have_xattr, b'Saving and restoring extended attributes (xattrs)')
    return EXIT_SUCCESS
