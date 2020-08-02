% bup-features(1) Bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-features - report the current status and capabilities of bup itself

# SYNOPSIS

bup features

# DESCRIPTION

`bup features` reports information about the current bup installation,
for example, which version of the Python interpreter is used, whether command
line editing is supported by `bup ftp`, or POSIX ACLs can be saved and
restored.

# EXAMPLES

    $ bup features
    bup 0.31~a7ff2d5b8c12b24b97858aad1251d28c18f8c1e1
    source a7ff2d5b8c12b24b97858aad1251d28c18f8c1e1 2020-07-05 14:54:06 -0500
        Python: 3.7.3
        Command line editing (e.g. bup ftp): yes
        Saving and restoring POSIX ACLs: yes
    ....

# SEE ALSO

`bup-version`(1)

# BUP

Part of the `bup`(1) suite.
