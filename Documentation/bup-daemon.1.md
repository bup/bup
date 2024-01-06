% bup-daemon(1) Bup %BUP_VERSION%
% Brandon Low <lostlogic@lostlogicx.com>
% %BUP_DATE%

# NAME

bup-daemon - listens for connections and runs `bup server`

# SYNOPSIS

bup daemon [-l address] [-p port]

# DESCRIPTION

`bup daemon` is a simple bup server which listens on a
socket and forks connections to `bup mux server` children.

# OPTIONS

-l, \--listen=*address*
:   the address or hostname to listen on

-p, \--port=*port*
:   the port to listen on

# BUP

Part of the `bup`(1) suite.
