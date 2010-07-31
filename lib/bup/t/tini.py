from wvtest import *
from bup import ini
from bup.helpers import *

testfile = """

# this is a comment
globaltest = 99

[test1]
a=b
z=x
b=c
# comment
[test2]
   # comment
   p=7

[test0]
q=3
  # another comment
"""

testfile_out = """

# this is a comment
globaltest = 99

[test1]
a = b
z = x
b = c
# comment

[test2]
# comment
p = 7

[test0]
q = 3
# another comment
"""

@wvtest
def test_ini():
    testlist = testfile.split('\n')
    c = ini.Ini()
    c.read(testlist)
    WVPASSEQ(list(c.keys()), ['', 'test1', 'test2', 'test0'])
    WVPASSEQ(c.get('', 'globaltest'), '99')
    WVPASSEQ(c.get('test1', 'b', 99), 'c')
    WVPASSEQ(list(c.section('test2').keys()), ['p'])
    WVPASSEQ(list(c.section('test1').keys()), ['a', 'z', 'b'])
    WVPASSEQ([i.value for i in c.section('test0').items()], ['3'])

    out = '\n'.join(c.write())
    WVPASSEQ(out, testfile_out)

    unlink('my.ini.tmp')
    cfile = ini.new('my.ini.tmp')
    cfile.set("a", "b", 99)
    cfile.set("p", "q", None)
    cfile.set("z", "z", "99.7")
    WVPASS(cfile.section('z').dirty)
    WVPASS(cfile.dirty)
    cfile.flush()

    WVPASSEQ(open('my.ini.tmp').read(), "[a]\nb = 99\n\n[z]\nz = 99.7\n")
