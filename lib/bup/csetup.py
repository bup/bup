from distutils.core import setup, Extension

_helpers_mod = Extension('_helpers', sources=['_helpers.c', 'bupsplit.c'])

setup(name='_helpers',
      version='0.1',
      description='accelerator library for bup',
      ext_modules=[_helpers_mod])
