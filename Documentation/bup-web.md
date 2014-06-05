% bup-ftp(1) Bup %BUP_VERSION%
% Joe Beda <jbeda@gmail.com>
% %BUP_DATE%

# NAME

bup-web - Start web server to browse bup repositiory

# SYNOPSIS

bup web [[hostname]:port]

# DESCRIPTION

`bup web` starts a web server that can browse bup repositories. The file
hierarchy is the same as that shown by `bup-fuse`(1), `bup-ls`(1) and
`bup-ftp`(1).

`hostname` and `port` default to 127.0.0.1 and 8080, respectively, and hence
`bup web` will only offer up the web server to locally running clients. If
you'd like to expose the web server to anyone on your network (dangerous!) you
can omit the bind address to bind to all available interfaces: `:8080`.

# OPTIONS

--human-readable
:   display human readable file sizes (i.e. 3.9K, 4.7M)

--browser
:   open the site in the default browser

# EXAMPLES

    $ bup web
    Serving HTTP on 127.0.0.1:8080...
    ^C

    $ bup web :8080
    Serving HTTP on 0.0.0.0:8080...
    ^C


# SEE ALSO

`bup-fuse`(1), `bup-ls`(1), `bup-ftp`(1), `bup-restore`(1)


# BUP

Part of the `bup`(1) suite.
