"""This is a separate module so we can cleanly getcwd() before anyone
   does chdir().
"""
import sys, os

startdir = os.getcwd()

def exe():
    return (os.environ.get('BUP_MAIN_EXE') or
            os.path.join(startdir, sys.argv[0]))

def exedir():
    return os.path.split(exe())[0]

def exefile():
    return os.path.split(exe())[1]
