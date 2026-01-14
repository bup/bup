
from bup import options
from bup.cmd import validate_refs
from bup.compat import argv_bytes


optspec = """
bup validate-ref-links [ref...]
--
v,verbose       increase log output (can be used more than once)
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    args = [argv[0]]
    args.extend([b'-v'] * (opt.verbose or 0))
    args.append(b'--links')
    args.extend(map(argv_bytes, extra))
    return validate_refs.main(args)
