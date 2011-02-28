#!/usr/bin/env python
import sys, os, re
from bup import options
from bup import _helpers   # fixes up sys.argv on import

optspec = """
bup newliner
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if extra:
    o.fatal("no arguments expected")

r = re.compile(r'([\r\n])')
lastlen = 0
all = ''
width = options._tty_width() or 78
while 1:
    l = r.split(all, 1)
    if len(l) <= 1:
        if len(all) >= 160:
            sys.stdout.write('%s\n' % all[:78])
            sys.stdout.flush()
            all = all[78:]
        try:
            b = os.read(sys.stdin.fileno(), 4096)
        except KeyboardInterrupt:
            break
        if not b:
            break
        all += b
    else:
        assert(len(l) == 3)
        (line, splitchar, all) = l
        if splitchar == '\r':
            line = line[:width]
        sys.stdout.write('%-*s%s' % (lastlen, line, splitchar))
        if splitchar == '\r':
            lastlen = len(line)
        else:
            lastlen = 0
        sys.stdout.flush()

if lastlen:
    sys.stdout.write('%-*s\r' % (lastlen, ''))
if all:
    sys.stdout.write('%s\n' % all)
