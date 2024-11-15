
from binascii import hexlify, unhexlify
from os import path
import glob, sys, zlib

from bup import options, git
from bup.compat import pairwise
from bup.helpers import \
    EXIT_FALSE, EXIT_TRUE, log, qprogress, reprogress, wrap_boolean_main
from bup.io import byte_stream, path_msg


optspec = """
bup validate-object-links
--
"""

def obj_type_and_data_ofs(buf):
    # cf. gitformat-pack(5)
    c = buf[0]
    kind = (c & 0x70) >> 4
    i = 0
    while c & 0x80:
        i += 1
        c = buf[i]
    return kind, i + 1

class Pack:
    def __init__(self, idx, cp):
        self._idx = idx
        self._cp = cp
        self._f = None

    def __enter__(self):
        assert self._f is None
        self._f = open(self._idx.name[:-3] + b'pack', 'rb', buffering=0)
        return self

    def __exit__(self, *args, **kw):
        self._f.close()
        self._f = None

    def __iter__(self):
        # cf. gitformat-pack(5)
        assert self._f
        assert self._f.read(8) == b'PACK\x00\x00\x00\x02'
        ofs_and_idxs = list(self._idx.oid_offsets_and_idxs())
        ofs_and_idxs.sort()
        ofs_and_idxs.append((-1, None)) # produces sz < 0 (i.e. read remaining)
        for obj, nextobj in pairwise(ofs_and_idxs):
            ofs, idx = obj
            nextofs, _ = nextobj
            self._f.seek(ofs)
            sz = nextofs - ofs
            hdr = self._f.read(5) # enough for 4GiB objects
            kind, data_ofs = obj_type_and_data_ofs(hdr)
            assert data_ofs > 0
            if kind == 3: # blob
                continue
            oid = self._idx._idx_to_hash(idx)
            if kind in (1, 2, 4): # commit tree tag
                data = hdr[data_ofs:] + self._f.read(sz - 5)
                data = zlib.decompress(data)
                yield oid, git._typermap[kind], data
            elif kind in (5, 6, 7): # reserved obj_ofs_delta obj_ref_delta
                it = self._cp.get(hexlify(oid))
                _, tp, _ = next(it)
                data = b''.join(it)
                if tp == b'blob':
                    continue
                yield oid, tp, data
            else: # *should* be impossible to reach (3-bits) for anything but 0
                pm = path_msg(self._idx.name)
                raise Exception(f'Invalid object type {kind} in {pm} at {idx}\n')

def validate(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])

    if extra:
        o.fatal("no arguments expected")

    git.check_repo_or_die()

    sys.stdout.flush()
    out = byte_stream(sys.stdout)
    cp = git.cp()
    ret = EXIT_TRUE
    with git.PackIdxList(git.repo(b'objects/pack')) as mi:
        idxlist = glob.glob(path.join(git.repo(b'objects/pack'), b'*.idx'))
        obj_n = 0
        for idxname in idxlist:
            with git.open_idx(idxname) as idx:
                obj_n += idx.nsha
        obj_i = 0
        for idxname in idxlist:
            with git.open_idx(idxname) as idx, Pack(idx, cp) as pack:
                for oid, tp, data in pack:
                    # bup doesn't generate tag objects
                    if tp == b'tag':
                        out.flush()
                        sys.stderr.flush()
                        log(f'warning: skipping tag object {oid.hex()}\n')
                        reprogress()
                        continue
                    if tp == b'tree':
                        shalist = (x[2] for x in git.tree_decode(data))
                    elif tp == b'commit':
                        commit = git.parse_commit(data)
                        shalist = map(unhexlify, commit.parents + [commit.tree])
                    else:
                        raise Exception(f'unexpected object type {tp}')
                    for suboid in shalist:
                        if not mi.exists(suboid):
                            out.write(b'no %s for %s\n'
                                      % (hexlify(suboid), hexlify(oid)))
                            ret = EXIT_FALSE
                            reprogress()
                obj_i += idx.nsha
                obj_frac = obj_i / obj_n
                qprogress(f'scanned {obj_i}/{obj_n} {obj_frac:.2%}\r')
    return ret

def main(argv):
    wrap_boolean_main(lambda: validate(argv))
