% bup-random(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-random - generate a stream of random output

# SYNOPSIS

bup random [-S seed] [-fv] \<numbytes\>

# DESCRIPTION

`bup random` produces a stream of pseudorandom output bytes to
stdout.  Note: the bytes are *not* generated using a
cryptographic algorithm and should never be used for
security.

Note that the stream of random bytes will be identical
every time `bup random` is run, unless you provide a
different `seed` value.  This is intentional: the purpose
of this program is to be able to run repeatable tests on
large amounts of data, so we want identical data every
time.

`bup random` generates about 240 megabytes per second on a
modern test system (Intel Core2), which is faster than you
could achieve by reading data from most disks.  Thus, it
can be helpful when running microbenchmarks.

# OPTIONS

\<numbytes\>
:   the number of bytes of data to generate.  Can be used
    with the suffices `k`, `M`, or `G` to indicate
    kilobytes, megabytes, or gigabytes, respectively.
    
-S, \--seed=*seed*
:   use the given value to seed the pseudorandom number
    generator.  The generated output stream will be
    identical for every stream seeded with the same value. 
    The default seed is 1.  A seed value of 0 is equivalent
    to 1.

-f, \--force
:   generate output even if stdout is a tty.  (Generating
    random data to a tty is generally considered
    ill-advised, but you can do if you really want.)
    
-v, \--verbose
:   print a progress message showing the number of bytes that
    has been output so far.

# EXAMPLES
    
    $ bup random 1k | sha1sum
    2108c55d0a2687c8dacf9192677c58437a55db71  -
    
    $ bup random -S1 1k | sha1sum
    2108c55d0a2687c8dacf9192677c58437a55db71  -
    
    $ bup random -S2 1k | sha1sum
    f71acb90e135d98dad7efc136e8d2cc30573e71a  -
    
    $ time bup random 1G >/dev/null
    Random: 1024 Mbytes, done.
    
    real   0m4.261s
    user   0m4.048s
    sys    0m0.172s
    
    $ bup random 1G | bup split -t --bench
    Random: 1024 Mbytes, done.
    bup: 1048576.00kbytes in 18.59 secs = 56417.78 kbytes/sec
    1092599b9c7b2909652ef1e6edac0796bfbfc573
    
# BUP

Part of the `bup`(1) suite.
