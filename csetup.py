from distutils.core import setup, Extension

chashsplit_mod = Extension('chashsplit', sources=['chashsplitmodule.c'])

setup(name='chashsplit',
      version='0.1',
      description='hashsplit helper library for bup',
      ext_modules=[chashsplit_mod])
