#!/usr/bin/env python
import sys, re, struct, time, resource
from bup import git, bloom, midx, options, _helpers
from bup.helpers import *

handle_ctrl_c()

_linux_warned = 0
def linux_memstat():
    global _linux_warned
    #fields = ['VmSize', 'VmRSS', 'VmData', 'VmStk', 'ms']
    d = {}
    try:
        f = open('/proc/self/status')
    except IOError, e:
        if not _linux_warned:
            log('Warning: %s\n' % e)
            _linux_warned = 1
        return {}
    for line in f:
        # Note that on Solaris, this file exists but is binary.  If that
        # happens, this split() might not return two elements.  We don't
        # really need to care about the binary format since this output
        # isn't used for much and report() can deal with missing entries.
        t = re.split(r':\s*', line.strip(), 1)
        if len(t) == 2:
            k,v = t
            d[k] = v
    return d


last = last_u = last_s = start = 0
def report(count):
    global last, last_u, last_s, start
    headers = ['RSS', 'MajFlt', 'user', 'sys', 'ms']
    ru = resource.getrusage(resource.RUSAGE_SELF)
    now = time.time()
    rss = int(ru.ru_maxrss/1024)
    if not rss:
        rss = linux_memstat().get('VmRSS', '??')
    fields = [rss,
              ru.ru_majflt,
              int((ru.ru_utime - last_u) * 1000),
              int((ru.ru_stime - last_s) * 1000),
              int((now - last) * 1000)]
    fmt = '%9s  ' + ('%10s ' * len(fields))
    if count >= 0:
        print fmt % tuple([count] + fields)
    else:
        start = now
        print fmt % tuple([''] + headers)
    sys.stdout.flush()
    
    # don't include time to run report() in usage counts
    ru = resource.getrusage(resource.RUSAGE_SELF)
    last_u = ru.ru_utime
    last_s = ru.ru_stime
    last = time.time()


optspec = """
bup memtest [-n elements] [-c cycles]
--
n,number=  number of objects per cycle [10000]
c,cycles=  number of cycles to run [100]
ignore-midx  ignore .midx files, use only .idx files
existing   test with existing objects instead of fake ones
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal('no arguments expected')

git.ignore_midx = opt.ignore_midx

git.check_repo_or_die()
m = git.PackIdxList(git.repo('objects/pack'))

report(-1)
_helpers.random_sha()
report(0)

if opt.existing:
    def foreverit(mi):
        while 1:
            for e in mi:
                yield e
    objit = iter(foreverit(m))
    
for c in xrange(opt.cycles):
    for n in xrange(opt.number):
        if opt.existing:
            bin = objit.next()
            assert(m.exists(bin))
        else:
            bin = _helpers.random_sha()

            # technically, a randomly generated object id might exist.
            # but the likelihood of that is the likelihood of finding
            # a collision in sha-1 by accident, which is so unlikely that
            # we don't care.
            assert(not m.exists(bin))
    report((c+1)*opt.number)

if bloom._total_searches:
    print ('bloom: %d objects searched in %d steps: avg %.3f steps/object' 
           % (bloom._total_searches, bloom._total_steps,
              bloom._total_steps*1.0/bloom._total_searches))
if midx._total_searches:
    print ('midx: %d objects searched in %d steps: avg %.3f steps/object' 
           % (midx._total_searches, midx._total_steps,
              midx._total_steps*1.0/midx._total_searches))
if git._total_searches:
    print ('idx: %d objects searched in %d steps: avg %.3f steps/object' 
           % (git._total_searches, git._total_steps,
              git._total_steps*1.0/git._total_searches))
print 'Total time: %.3fs' % (time.time() - start)
