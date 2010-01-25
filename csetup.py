from distutils.core import setup, Extension

_hashsplit_mod = Extension('_hashsplit', sources=['_hashsplit.c'])

setup(name='_hashsplit',
      version='0.1',
      description='hashsplit helper library for bup',
      ext_modules=[_hashsplit_mod])
