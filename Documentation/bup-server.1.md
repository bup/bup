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

The server's resource usage can be limited by setting
`bup.server.deduplicate-writes` to `false`.  See the description in
`bup-config(5)` for additional information.

# FILES

$BUP_DIR/bup-dumb-server
:   When this file exists, `bup` will act as if
    `bup.server.deduplicate-writes` is set to `false` in the
    configuration, unless the configuration already specifies a value.

# SEE ALSO

`bup-save`(1), `bup-split`(1), `bup-config`(1)

# BUP

Part of the `bup`(1) suite.
