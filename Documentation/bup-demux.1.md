% bup-demux(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-demux - demultiplexes data and error streams from standard input

# SYNOPSIS

bup demux

# DESCRIPTION

Note: this is an internal command, and may be removed or changed at
any time.

`bup demux` reads standard input as a bup "multiplexed" stream of
data from standard output and standard error, and reproduces that
output on its own standard output and standard error.  It's primary
purpose is to support `bup-on`(1).

# SEE ALSO

`bup-on`(1), `bup-mux`(1)

# BUP

Part of the `bup`(1) suite.
