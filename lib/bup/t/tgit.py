import struct, os, tempfile, time
from bup import git
from bup.helpers import *
from wvtest import *


@wvtest
def testmangle():
    afile  = 0100644
    afile2 = 0100770
    alink  = 0120000
    adir   = 0040000
    adir2  = 0040777
    WVPASSEQ(git.mangle_name("a", adir2, adir), "a")
    WVPASSEQ(git.mangle_name(".bup", adir2, adir), ".bup.bupl")
    WVPASSEQ(git.mangle_name("a.bupa", adir2, adir), "a.bupa.bupl")
    WVPASSEQ(git.mangle_name("b.bup", alink, alink), "b.bup.bupl")
    WVPASSEQ(git.mangle_name("b.bu", alink, alink), "b.bu")
    WVPASSEQ(git.mangle_name("f", afile, afile2), "f")
    WVPASSEQ(git.mangle_name("f.bup", afile, afile2), "f.bup.bupl")
    WVPASSEQ(git.mangle_name("f.bup", afile, adir), "f.bup.bup")
    WVPASSEQ(git.mangle_name("f", afile, adir), "f.bup")

    WVPASSEQ(git.demangle_name("f.bup"), ("f", git.BUP_CHUNKED))
    WVPASSEQ(git.demangle_name("f.bupl"), ("f", git.BUP_NORMAL))
    WVPASSEQ(git.demangle_name("f.bup.bupl"), ("f.bup", git.BUP_NORMAL))

    # for safety, we ignore .bup? suffixes we don't recognize.  Future
    # versions might implement a .bup[a-z] extension as something other
    # than BUP_NORMAL.
    WVPASSEQ(git.demangle_name("f.bupa"), ("f.bupa", git.BUP_NORMAL))


@wvtest
def testencode():
    s = 'hello world'
    looseb = ''.join(git._encode_looseobj('blob', s))
    looset = ''.join(git._encode_looseobj('tree', s))
    loosec = ''.join(git._encode_looseobj('commit', s))
    packb = ''.join(git._encode_packobj('blob', s))
    packt = ''.join(git._encode_packobj('tree', s))
    packc = ''.join(git._encode_packobj('commit', s))
    WVPASSEQ(git._decode_looseobj(looseb), ('blob', s))
    WVPASSEQ(git._decode_looseobj(looset), ('tree', s))
    WVPASSEQ(git._decode_looseobj(loosec), ('commit', s))
    WVPASSEQ(git._decode_packobj(packb), ('blob', s))
    WVPASSEQ(git._decode_packobj(packt), ('tree', s))
    WVPASSEQ(git._decode_packobj(packc), ('commit', s))


@wvtest
def testpacks():
    git.init_repo('pybuptest.tmp')
    git.verbose = 1

    now = str(time.time())  # hopefully not in any packs yet
    w = git.PackWriter()
    w.write('blob', now)
    w.write('blob', now)
    w.abort()
    
    w = git.PackWriter()
    hashes = []
    nobj = 1000
    for i in range(nobj):
        hashes.append(w.write('blob', str(i)))
    log('\n')
    nameprefix = w.close()
    print repr(nameprefix)
    WVPASS(os.path.exists(nameprefix + '.pack'))
    WVPASS(os.path.exists(nameprefix + '.idx'))

    r = git.open_idx(nameprefix + '.idx')
    print repr(r.fanout)

    for i in range(nobj):
        WVPASS(r.find_offset(hashes[i]) > 0)
    WVPASS(r.exists(hashes[99]))
    WVFAIL(r.exists('\0'*20))

    pi = iter(r)
    for h in sorted(hashes):
        WVPASSEQ(str(pi.next()).encode('hex'), h.encode('hex'))

    WVFAIL(r.find_offset('\0'*20))

    r = git.PackIdxList('pybuptest.tmp/objects/pack')
    WVPASS(r.exists(hashes[5]))
    WVPASS(r.exists(hashes[6]))
    WVFAIL(r.exists('\0'*20))

@wvtest
def test_long_index():
    w = git.PackWriter()
    obj_bin = struct.pack('!IIIII',
            0x00112233, 0x44556677, 0x88990011, 0x22334455, 0x66778899)
    obj2_bin = struct.pack('!IIIII',
            0x11223344, 0x55667788, 0x99001122, 0x33445566, 0x77889900)
    obj3_bin = struct.pack('!IIIII',
            0x22334455, 0x66778899, 0x00112233, 0x44556677, 0x88990011)
    pack_bin = struct.pack('!IIIII',
            0x99887766, 0x55443322, 0x11009988, 0x77665544, 0x33221100)
    idx = list(list() for i in xrange(256))
    idx[0].append((obj_bin, 1, 0xfffffffff))
    idx[0x11].append((obj2_bin, 2, 0xffffffffff))
    idx[0x22].append((obj3_bin, 3, 0xff))
    (fd,name) = tempfile.mkstemp(suffix='.idx', dir=git.repo('objects'))
    f = os.fdopen(fd, 'w+b')
    r = w._write_pack_idx_v2(f, idx, pack_bin)
    f.seek(0)
    i = git.PackIdxV2(name, f)
    WVPASSEQ(i.find_offset(obj_bin), 0xfffffffff)
    WVPASSEQ(i.find_offset(obj2_bin), 0xffffffffff)
    WVPASSEQ(i.find_offset(obj3_bin), 0xff)
    f.close()
    os.remove(name)
