% bup-mux(1) Bup %BUP_VERSION%
% Brandon Low <lostlogic@lostlogicx.com>
% %BUP_DATE%

# NAME

bup-mux - multiplexes data and error streams over a connection

# SYNOPSIS

bup mux \<command\> [options...]

# DESCRIPTION

`bup mux` is used in the bup client-server protocol to
send both data and debugging/error output over the single
connection stream.

`bup mux bup server` might be used in an inetd server setup.

# OPTIONS

command
:   the command to run
options
:   options for the command

# BUP

Part of the `bup`(1) suite.
