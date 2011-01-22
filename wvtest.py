#!/usr/bin/env python
import traceback
import os
import re
import sys

if __name__ != "__main__":   # we're imported as a module
    _registered = []
    _tests = 0
    _fails = 0

    def wvtest(func):
        """ Use this decorator (@wvtest) in front of any function you want to run
            as part of the unit test suite.  Then run:
                python wvtest.py path/to/yourtest.py
            to run all the @wvtest functions in that file.
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
        print '! %-70s %s' % ('%s:%-4d %s' % (filename, line, msg),
                              code)
        sys.stdout.flush()


    def _check(cond, msg = 'unknown', tb = None):
        if tb == None: tb = traceback.extract_stack()[-3]
        if cond:
            _result(msg, tb, 'ok')
        else:
            _result(msg, tb, 'FAILED')
        return cond


    def _code():
        (filename, line, func, text) = traceback.extract_stack()[-3]
        text = re.sub(r'^\w+\((.*)\)(\s*#.*)?$', r'\1', text);
        return text


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
        except etype, e:
            return _check(True, 'EXCEPT(%s)' % _code())
        except:
            _check(False, 'EXCEPT(%s)' % _code())
            raise
        else:
            return _check(False, 'EXCEPT(%s)' % _code())

else:  # we're the main program
    # NOTE
    # Why do we do this in such a convoluted way?  Because if you run
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
    import wvtest

    def _runtest(modname, fname, f):
        print
        print 'Testing "%s" in %s.py:' % (fname, modname)
        sys.stdout.flush()
        try:
            f()
        except Exception, e:
            print
            print traceback.format_exc()
            tb = sys.exc_info()[2]
            wvtest._result(e, traceback.extract_tb(tb)[1], 'EXCEPTION')

    # main code
    for modname in sys.argv[1:]:
        if not os.path.exists(modname):
            print 'Skipping: %s' % modname
            continue
        if modname.endswith('.py'):
            modname = modname[:-3]
        print 'Importing: %s' % modname
        wvtest._registered = []
        oldwd = os.getcwd()
        oldpath = sys.path
        try:
            path, mod = os.path.split(os.path.abspath(modname))
            os.chdir(path)
            sys.path += [path, os.path.split(path)[0]]
            mod = __import__(modname.replace(os.path.sep, '.'), None, None, [])
            for t in wvtest._registered:
                _runtest(modname, t.func_name, t)
                print
        finally:
            os.chdir(oldwd)
            sys.path = oldpath

    print
    print 'WvTest: %d tests, %d failures.' % (wvtest._tests, wvtest._fails)
