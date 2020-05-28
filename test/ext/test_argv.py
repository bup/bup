
from __future__ import absolute_import, print_function

from random import randint
from subprocess import CalledProcessError, check_output
from sys import stderr, stdout


from test.lib.wvpytest import wvpasseq

def rand_bytes(n):
    return bytes([randint(1, 255) for x in range(n)])

def test_argv():
    for trial in range(100):
        cmd = [b'dev/echo-argv-bytes', rand_bytes(randint(1, 32))]
        out = check_output(cmd)
        wvpasseq(b'\0\n'.join(cmd) + b'\0\n', out)
