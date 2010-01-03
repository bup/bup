import sys, os, pwd, subprocess


def log(s):
    sys.stderr.write(s)


def readpipe(argv):
    p = subprocess.Popen(argv, stdout=subprocess.PIPE)
    r = p.stdout.read()
    p.wait()
    return r


_username = None
def username():
    global _username
    if not _username:
        uid = os.getuid()
        try:
            _username = pwd.getpwuid(uid)[0]
        except KeyError:
            _username = 'user%d' % uid
    return _username


_userfullname = None
def userfullname():
    global _userfullname
    if not _userfullname:
        uid = os.getuid()
        try:
            _userfullname = pwd.getpwuid(uid)[4].split(',')[0]
        except KeyError:
            _userfullname = 'user%d' % uid
    return _userfullname


_hostname = None
def hostname():
    global _hostname
    if not _hostname:
        try:
            _hostname = readpipe(['hostname', '-f']).strip()
        except OSError:
            pass
    return _hostname or 'localhost'


def linereader(f):
    while 1:
        line = f.readline()
        if not line:
            break
        yield line[:-1]
