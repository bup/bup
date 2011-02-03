#!/usr/bin/env python
import sys, getopt, socket, subprocess
from bup import options, path
from bup.helpers import *

optspec = """
bup daemon [options...]
--
l,listen  ip address to listen on, defaults to *
p,port    port to listen on, defaults to 1982
"""
o = options.Options(optspec, optfunc=getopt.getopt)
(opt, flags, extra) = o.parse(sys.argv[1:])
if extra:
    o.fatal('no arguments expected')

host = opt.listen
port = opt.port and int(opt.port) or 1982

import socket
import sys

socks = []
for res in socket.getaddrinfo(host, port, socket.AF_UNSPEC,
                              socket.SOCK_STREAM, 0, socket.AI_PASSIVE):
    af, socktype, proto, canonname, sa = res
    try:
        s = socket.socket(af, socktype, proto)
    except socket.error, msg:
        continue
    try:
        if af == socket.AF_INET6:
            debug1("bup daemon: listening on [%s]:%s\n" % sa[:2])
        else:
            debug1("bup daemon: listening on %s:%s\n" % sa[:2])
        s.bind(sa)
        s.listen(1)
    except socket.error, msg:
        s.close()
        continue
    socks.append(s)

if not socks:
    log('bup daemon: could not open socket\n')
    sys.exit(1)

try:
    while True:
        [rl,wl,xl] = select.select(socks, [], [], 60)
        for l in rl:
            s, src = l.accept()
            log("Socket accepted connection from %s\n" % (src,))
            sp = subprocess.Popen([path.exe(), 'mux', 'server'],
                                  stdin=os.dup(s.fileno()), stdout=os.dup(s.fileno()))
            s.close()
finally:
    for l in socks:
        l.shutdown(socket.SHUT_RDWR)
        l.close()

debug1("bup daemon: done")
