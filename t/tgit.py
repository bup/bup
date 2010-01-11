import git, time
from wvtest import *
from helpers import *


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
    for i in range(1000):
        hashes.append(w.write('blob', str(i)))
    log('\n')
    nameprefix = w.close()
    print repr(nameprefix)
    WVPASS(os.path.exists(nameprefix + '.pack'))
    WVPASS(os.path.exists(nameprefix + '.idx'))

    r = git.PackIndex(nameprefix + '.idx')
    print repr(r.fanout)

    for i in range(1000):
        WVPASS(r.find_offset(hashes[i]) > 0)
    WVPASS(r.exists(hashes[99]))
    WVFAIL(r.exists('\0'*20))

    WVFAIL(r.find_offset('\0'*20))

    r = git.MultiPackIndex('pybuptest.tmp/objects/pack')
    WVPASS(r.exists(hashes[5]))
    WVPASS(r.exists(hashes[6]))
    WVFAIL(r.exists('\0'*20))
