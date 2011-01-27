% bup-daemon(1) Bup %BUP_VERSION%
% Brandon Low <lostlogic@lostlogicx.com>
% %BUP_DATE%

# NAME

bup-daemon - listens for connections and runs `bup server`

# SYNOPSIS

bup daemon

# DESCRIPTION

`bup daemon` is a simple bup server which listens on a
socket and forks connections to `bup mux server` children.

# BUP

Part of the `bup`(1) suite.
