
from __future__ import absolute_import

from distutils.core import setup, Extension

_helpers_mod = Extension('_helpers',
                         sources=['_helpers.c', 'bupsplit.c'],
                         depends=['../../config/config.h', 'bupsplit.h'])

setup(name='_helpers',
      version='0.1',
      description='accelerator library for bup',
      ext_modules=[_helpers_mod])
