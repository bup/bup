% bup-tick(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-tick - wait for up to one second

# SYNOPSIS

bup tick

# DESCRIPTION

`bup tick` waits until `time`(2) returns a different value
than it originally did.  Since time() has a granularity of
one second, this can cause a delay of up to one second.

This program is useful for writing tests that need to
ensure a file date will be seen as modified.  It is
slightly better than `sleep`(1) since it sometimes waits
for less than one second.

# EXAMPLES

    $ date; bup tick; date
    Sat Feb  6 16:59:58 EST 2010
    Sat Feb  6 16:59:59 EST 2010
    
# BUP

Part of the `bup`(1) suite.
