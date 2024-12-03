
from __future__ import absolute_import, print_function
from binascii import hexlify, unhexlify
import sys

from bup import git, options
from bup.compat import argv_bytes
from bup.helpers import add_error, handle_ctrl_c, log, qprogress, saved_errors
from bup.io import byte_stream

optspec = """
bup list-idx [--find=<prefix>] <idxfilenames...>
--
find=   display only objects that start with <prefix>
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])

    handle_ctrl_c()

    opt.find = argv_bytes(opt.find) if opt.find else b''

    if not extra:
        o.fatal('you must provide at least one filename')

    if len(opt.find) > 40:
        o.fatal('--find parameter must be <= 40 chars long')
    else:
        if len(opt.find) % 2:
            s = opt.find + b'0'
        else:
            s = opt.find
        try:
            bin = unhexlify(s)
        except TypeError:
            o.fatal('--find parameter is not a valid hex string')

    sys.stdout.flush()
    out = byte_stream(sys.stdout)
    find = opt.find.lower()
    count = 0
    idxfiles = [argv_bytes(x) for x in extra]
    for name in idxfiles:
        ix = None
        try:
            ix = git.open_object_idx(name)
        except git.GitError as e:
            add_error('%r: %s' % (name, e))
        if not ix:
            continue
        with ix:
            if len(opt.find) == 40:
                if ix.exists(bin):
                    out.write(b'%s %s\n' % (name, find))
            else:
                # slow, exhaustive search
                for _i in ix:
                    i = hexlify(_i)
                    if i.startswith(find):
                        out.write(b'%s %s\n' % (name, i))
                    qprogress('Searching: %d\r' % count)
                    count += 1

    if saved_errors:
        log('WARNING: %d errors encountered while saving.\n' % len(saved_errors))
        sys.exit(1)
