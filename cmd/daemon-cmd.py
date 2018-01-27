#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import
import sys, getopt, socket, subprocess, fcntl
from bup import options, path
from bup.helpers import *

optspec = """
bup daemon [options...] -- [bup-server options...]
--
l,listen  ip address to listen on, defaults to *
p,port    port to listen on, defaults to 1982
"""
o = options.Options(optspec, optfunc=getopt.getopt)
(opt, flags, extra) = o.parse(sys.argv[1:])

host = opt.listen
port = opt.port and int(opt.port) or 1982

import socket
import sys

socks = []
e = None
for res in socket.getaddrinfo(host, port, socket.AF_UNSPEC,
                              socket.SOCK_STREAM, 0, socket.AI_PASSIVE):
    af, socktype, proto, canonname, sa = res
    try:
        s = socket.socket(af, socktype, proto)
    except socket.error as e:
        continue
    try:
        if af == socket.AF_INET6:
            log("bup daemon: listening on [%s]:%s\n" % sa[:2])
        else:
            log("bup daemon: listening on %s:%s\n" % sa[:2])
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(sa)
        s.listen(1)
        fcntl.fcntl(s.fileno(), fcntl.F_SETFD, fcntl.FD_CLOEXEC)
    except socket.error as e:
        s.close()
        continue
    socks.append(s)

if not socks:
    log('bup daemon: listen socket: %s\n' % e.args[1])
    sys.exit(1)

try:
    while True:
        [rl,wl,xl] = select.select(socks, [], [], 60)
        for l in rl:
            s, src = l.accept()
            try:
                log("Socket accepted connection from %s\n" % (src,))
                fd1 = os.dup(s.fileno())
                fd2 = os.dup(s.fileno())
                s.close()
                sp = subprocess.Popen([path.exe(), 'mux', '--',
                                       path.exe(), 'server']
                                      + extra, stdin=fd1, stdout=fd2)
            finally:
                os.close(fd1)
                os.close(fd2)
finally:
    for l in socks:
        l.shutdown(socket.SHUT_RDWR)
        l.close()

debug1("bup daemon: done")
