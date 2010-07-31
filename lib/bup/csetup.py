from distutils.core import setup, Extension

_faster_mod = Extension('_faster', sources=['_faster.c', 'bupsplit.c'])

setup(name='_faster',
      version='0.1',
      description='accelerator library for bup',
      ext_modules=[_faster_mod])
