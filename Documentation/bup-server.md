% bup-server(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-server - the server side of the bup client-server relationship

# SYNOPSIS

bup server

# DESCRIPTION

`bup server` is the server side of a remote bup session. 
If you use `bup-split`(1) or `bup-save`(1) with the `-r`
option, they will ssh to the remote server and run `bup
server` to receive the transmitted objects.

There is normally no reason to run `bup server` yourself.

# SEE ALSO

`bup-save`(1), `bup-split`(1)

# BUP

Part of the `bup`(1) suite.
