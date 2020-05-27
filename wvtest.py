#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/dev/bup-python"
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

#
# WvTest:
#   Copyright (C)2007-2012 Versabanq Innovations Inc. and contributors.
#       Licensed under the GNU Library General Public License, version 2.
#       See the included file named LICENSE for license information.
#       You can get wvtest from: http://github.com/apenwarr/wvtest
#

from __future__ import absolute_import, print_function
from os.path import relpath
import atexit
import inspect
import os
import re
import sys
import traceback

sys.path[:0] = [os.path.realpath('test/lib')]

_start_dir = os.getcwd()

# NOTE
# Why do we do we need the "!= main" check?  Because if you run
# wvtest.py as a main program and it imports your test files, then
# those test files will try to import the wvtest module recursively.
# That actually *works* fine, because we don't run this main program
# when we're imported as a module.  But you end up with two separate
# wvtest modules, the one that gets imported, and the one that's the
# main program.  Each of them would have duplicated global variables
# (most importantly, wvtest._registered), and so screwy things could
# happen.  Thus, we make the main program module *totally* different
# from the imported module.  Then we import wvtest (the module) into
# wvtest (the main program) here and make sure to refer to the right
# versions of global variables.
#
# All this is done just so that wvtest.py can be a single file that's
# easy to import into your own applications.
if __name__ != '__main__':   # we're imported as a module
    _registered = []
    _tests = 0
    _fails = 0

    def wvtest(func):
        """ Use this decorator (@wvtest) in front of any function you want to
            run as part of the unit test suite.  Then run:
                python wvtest.py path/to/yourtest.py [other test.py files...]
            to run all the @wvtest functions in the given file(s).
        """
        _registered.append(func)
        return func


    def _result(msg, tb, code):
        global _tests, _fails
        _tests += 1
        if code != 'ok':
            _fails += 1
        (filename, line, func, text) = tb
        filename = os.path.basename(filename)
        msg = re.sub(r'\s+', ' ', str(msg))
        sys.stderr.flush()
        print('! %-70s %s' % ('%s:%-4d %s' % (filename, line, msg),
                              code))
        sys.stdout.flush()


    def _caller_stack(wv_call_depth):
        # Without the chdir, the source text lookup may fail
        orig = os.getcwd()
        os.chdir(_start_dir)
        try:
            return traceback.extract_stack()[-(wv_call_depth + 2)]
        finally:
            os.chdir(orig)


    def _check(cond, msg = 'unknown', tb = None):
        if tb == None: tb = _caller_stack(2)
        if cond:
            _result(msg, tb, 'ok')
        else:
            _result(msg, tb, 'FAILED')
        return cond

    def wvcheck(cond, msg, tb = None):
        if tb == None: tb = _caller_stack(2)
        if cond:
            _result(msg, tb, 'ok')
        else:
            _result(msg, tb, 'FAILED')
        return cond

    _code_rx = re.compile(r'^\w+\((.*)\)(\s*#.*)?$')
    def _code():
        text = _caller_stack(2)[3]
        return _code_rx.sub(r'\1', text)

    def WVSTART(message):
        filename = _caller_stack(1)[0]
        sys.stderr.write('Testing \"' + message + '\" in ' + filename + ':\n')

    def WVMSG(message):
        ''' Issues a notification. '''
        return _result(message, _caller_stack(1), 'ok')

    def WVPASS(cond = True):
        ''' Counts a test failure unless cond is true. '''
        return _check(cond, _code())

    def WVFAIL(cond = True):
        ''' Counts a test failure  unless cond is false. '''
        return _check(not cond, 'NOT(%s)' % _code())

    def WVPASSEQ(a, b):
        ''' Counts a test failure unless a == b. '''
        return _check(a == b, '%s == %s' % (repr(a), repr(b)))

    def WVPASSNE(a, b):
        ''' Counts a test failure unless a != b. '''
        return _check(a != b, '%s != %s' % (repr(a), repr(b)))

    def WVPASSLT(a, b):
        ''' Counts a test failure unless a < b. '''
        return _check(a < b, '%s < %s' % (repr(a), repr(b)))

    def WVPASSLE(a, b):
        ''' Counts a test failure unless a <= b. '''
        return _check(a <= b, '%s <= %s' % (repr(a), repr(b)))

    def WVPASSGT(a, b):
        ''' Counts a test failure unless a > b. '''
        return _check(a > b, '%s > %s' % (repr(a), repr(b)))

    def WVPASSGE(a, b):
        ''' Counts a test failure unless a >= b. '''
        return _check(a >= b, '%s >= %s' % (repr(a), repr(b)))

    def WVEXCEPT(etype, func, *args, **kwargs):
        ''' Counts a test failure unless func throws an 'etype' exception.
            You have to spell out the function name and arguments, rather than
            calling the function yourself, so that WVEXCEPT can run before
            your test code throws an exception.
        '''
        try:
            func(*args, **kwargs)
        except etype as e:
            return _check(True, 'EXCEPT(%s)' % _code())
        except:
            _check(False, 'EXCEPT(%s)' % _code())
            raise
        else:
            return _check(False, 'EXCEPT(%s)' % _code())

    wvstart = WVSTART
    wvmsg = WVMSG
    wvpass = WVPASS
    wvfail = WVFAIL
    wvpasseq = WVPASSEQ
    wvpassne = WVPASSNE
    wvpaslt = WVPASSLT
    wvpassle = WVPASSLE
    wvpassgt = WVPASSGT
    wvpassge = WVPASSGE
    wvexcept = WVEXCEPT

    def wvfailure_count():
        return _fails

    def _check_unfinished():
        if _registered:
            for func in _registered:
                print('WARNING: not run: %r' % (func,))
            WVFAIL('wvtest_main() not called')
        if _fails:
            sys.exit(1)

    atexit.register(_check_unfinished)


def _run_in_chdir(path, func, *args, **kwargs):
    oldwd = os.getcwd()
    oldpath = sys.path
    try:
        os.chdir(path)
        sys.path += [path, os.path.split(path)[0]]
        return func(*args, **kwargs)
    finally:
        os.chdir(oldwd)
        sys.path = oldpath


def _runtest(fname, f):
    mod = inspect.getmodule(f)
    rpath = relpath(mod.__file__, os.getcwd()).replace('.pyc', '.py')
    print()
    print('Testing "%s" in %s:' % (fname, rpath))
    sys.stdout.flush()
    try:
        _run_in_chdir(os.path.split(mod.__file__)[0], f)
    except Exception as e:
        print()
        print(traceback.format_exc())
        tb = sys.exc_info()[2]
        wvtest._result(e, traceback.extract_tb(tb)[1], 'EXCEPTION')


def _run_registered_tests():
    import wvtest as _wvtestmod
    while _wvtestmod._registered:
        t = _wvtestmod._registered.pop(0)
        _runtest(t.__name__, t)
        print()


def wvtest_main(extra_testfiles=tuple()):
    import wvtest as _wvtestmod
    _run_registered_tests()
    for modname in extra_testfiles:
        if not os.path.exists(modname):
            print('Skipping: %s' % modname)
            continue
        if modname.endswith('.py'):
            modname = modname[:-3]
        print('Importing: %s' % modname)
        path, mod = os.path.split(os.path.abspath(modname))
        nicename = modname.replace(os.path.sep, '.')
        while nicename.startswith('.'):
            nicename = modname[1:]
        _run_in_chdir(path, __import__, nicename, None, None, [])
        _run_registered_tests()
    print()
    print('WvTest: %d tests, %d failures.' % (_wvtestmod._tests,
                                              _wvtestmod._fails))


if __name__ == '__main__':
    import wvtest as _wvtestmod
    sys.modules['wvtest'] = _wvtestmod
    sys.modules['wvtest.wvtest'] = _wvtestmod
    wvtest = _wvtestmod
    wvtest_main(sys.argv[1:])
