
from __future__ import absolute_import

from wvpytest import *

from bup import options


def test_optdict():
    d = options.OptDict({
        'x': ('x', False),
        'y': ('y', False),
        'z': ('z', False),
        'other_thing': ('other_thing', False),
        'no_other_thing': ('other_thing', True),
        'no_z': ('z', True),
        'no_smart': ('smart', True),
        'smart': ('smart', False),
        'stupid': ('smart', True),
        'no_smart': ('smart', False),
    })
    WVPASS('foo')
    d['x'] = 5
    d['y'] = 4
    d['z'] = 99
    d['no_other_thing'] = 5
    WVPASSEQ(d.x, 5)
    WVPASSEQ(d.y, 4)
    WVPASSEQ(d.z, 99)
    WVPASSEQ(d.no_z, False)
    WVPASSEQ(d.no_other_thing, True)
    WVEXCEPT(KeyError, lambda: d.p)


invalid_optspec0 = """
"""


invalid_optspec1 = """
prog <whatever>
"""


invalid_optspec2 = """
--
x,y
"""


def test_invalid_optspec():
    WVPASS(options.Options(invalid_optspec0).parse([]))
    WVPASS(options.Options(invalid_optspec1).parse([]))
    WVPASS(options.Options(invalid_optspec2).parse([]))


optspec = """
prog <optionset> [stuff...]
prog [-t] <boggle>
--
t       test
q,quiet   quiet
l,longoption=   long option with parameters and a really really long description that will require wrapping
p= short option with parameters
onlylong  long option with no short
neveropt never called options
deftest1=  a default option with default [1]
deftest2=  a default option with [1] default [2]
deftest3=  a default option with [3] no actual default
deftest4=  a default option with [[square]]
deftest5=  a default option with "correct" [[square]
s,smart,no-stupid  disable stupidity
x,extended,no-simple   extended mode [2]
#,compress=  set compression level [5]
"""

def test_options():
    o = options.Options(optspec)
    (opt,flags,extra) = o.parse(['-tttqp', 7, '--longoption', '19',
                                 'hanky', '--onlylong', '-7'])
    WVPASSEQ(flags[0], ('-t', ''))
    WVPASSEQ(flags[1], ('-t', ''))
    WVPASSEQ(flags[2], ('-t', ''))
    WVPASSEQ(flags[3], ('-q', ''))
    WVPASSEQ(flags[4], ('-p', 7))
    WVPASSEQ(flags[5], ('--longoption', '19'))
    WVPASSEQ(extra, ['hanky'])
    WVPASSEQ((opt.t, opt.q, opt.p, opt.l, opt.onlylong,
              opt.neveropt), (3,1,7,19,1,None))
    WVPASSEQ((opt.deftest1, opt.deftest2, opt.deftest3, opt.deftest4,
              opt.deftest5), (1,2,None,None,'[square'))
    WVPASSEQ((opt.stupid, opt.no_stupid), (True, None))
    WVPASSEQ((opt.smart, opt.no_smart), (None, True))
    WVPASSEQ((opt.x, opt.extended, opt.no_simple), (2,2,2))
    WVPASSEQ((opt.no_x, opt.no_extended, opt.simple), (False,False,False))
    WVPASSEQ(opt['#'], 7)
    WVPASSEQ(opt.compress, 7)

    (opt,flags,extra) = o.parse(['--onlylong', '-t', '--no-onlylong',
                                 '--smart', '--simple'])
    WVPASSEQ((opt.t, opt.q, opt.onlylong), (1, None, 0))
    WVPASSEQ((opt.stupid, opt.no_stupid), (False, True))
    WVPASSEQ((opt.smart, opt.no_smart), (True, False))
    WVPASSEQ((opt.x, opt.extended, opt.no_simple), (0,0,0))
    WVPASSEQ((opt.no_x, opt.no_extended, opt.simple), (True,True,True))
