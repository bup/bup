
from __future__ import absolute_import, print_function

import shlex, sys
from distutils.core import setup, Extension
import os

if len(sys.argv) != 4:
    print('Usage: csetup.py CFLAGS LDFLAGS', file=sys.stderr)
    sys.exit(2)
_helpers_cflags = shlex.split(sys.argv[2])
_helpers_ldflags = shlex.split(sys.argv[3])
sys.argv = sys.argv[:2]

_helpers_mod = Extension('_helpers',
                         sources=['_helpers.c', 'bupsplit.c'],
                         depends=['../../config/config.h', 'bupsplit.h'],
                         extra_compile_args=_helpers_cflags,
                         extra_link_args=_helpers_ldflags)

setup(name='_helpers',
      version='0.1',
      description='accelerator library for bup',
      ext_modules=[_helpers_mod])
