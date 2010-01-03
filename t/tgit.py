import git
from wvtest import *


@wvtest
def testpacks():
    w = git.PackWriter()
    hashes = []
    for i in range(1000):
        hashes.append(w.easy_write('blob', str(i)))
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

    r = git.MultiPackIndex('.git/objects/pack')
    WVPASS(r.exists(hashes[5]))
    WVPASS(r.exists(hashes[6]))
    WVFAIL(r.exists('\0'*20))
