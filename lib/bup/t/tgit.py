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
    os.environ['BUP_MAIN_EXE'] = bupmain = '../../../bup'
    os.environ['BUP_DIR'] = bupdir = 'pybuptest.tmp'
    subprocess.call(['rm','-rf', bupdir])
    git.init_repo(bupdir)
    git.verbose = 1

    w = git.PackWriter()
    w.new_blob(os.urandom(100))
    w.new_blob(os.urandom(100))
    w.abort()
    
    w = git.PackWriter()
    hashes = []
    nobj = 1000
    for i in range(nobj):
        hashes.append(w.new_blob(str(i)))
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
def test_pack_name_lookup():
    os.environ['BUP_MAIN_EXE'] = bupmain = '../../../bup'
    os.environ['BUP_DIR'] = bupdir = 'pybuptest.tmp'
    subprocess.call(['rm','-rf', bupdir])
    git.init_repo(bupdir)
    git.verbose = 1
    packdir = git.repo('objects/pack')

    idxnames = []
    hashes = []

    for start in range(0,28,2):
        w = git.PackWriter()
        for i in range(start, start+2):
            hashes.append(w.new_blob(str(i)))
        log('\n')
        idxnames.append(os.path.basename(w.close() + '.idx'))

    r = git.PackIdxList(packdir)
    WVPASSEQ(len(r.packs), 2)
    for e,idxname in enumerate(idxnames):
        for i in range(e*2, (e+1)*2):
            WVPASSEQ(r.exists(hashes[i], want_source=True), idxname)


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
    os.close(fd)
    w.count = 3
    r = w._write_pack_idx_v2(name, idx, pack_bin)
    i = git.PackIdxV2(name, open(name, 'rb'))
    WVPASSEQ(i.find_offset(obj_bin), 0xfffffffff)
    WVPASSEQ(i.find_offset(obj2_bin), 0xffffffffff)
    WVPASSEQ(i.find_offset(obj3_bin), 0xff)
    os.remove(name)


@wvtest
def test_check_repo_or_die():
    git.check_repo_or_die()
    WVPASS('check_repo_or_die')  # if we reach this point the call above passed

    os.rename('pybuptest.tmp/objects/pack', 'pybuptest.tmp/objects/pack.tmp')
    open('pybuptest.tmp/objects/pack', 'w').close()
    try:
        git.check_repo_or_die()
    except SystemExit, e:
        WVPASSEQ(e.code, 14)
    else:
        WVFAIL()
    os.unlink('pybuptest.tmp/objects/pack')
    os.rename('pybuptest.tmp/objects/pack.tmp', 'pybuptest.tmp/objects/pack')

    try:
        git.check_repo_or_die('nonexistantbup.tmp')
    except SystemExit, e:
        WVPASSEQ(e.code, 15)
    else:
        WVFAIL()
