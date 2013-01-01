% bup-newliner(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-newliner - make sure progress messages don't overlap with output

# SYNOPSIS

\<any command\> 2>&1 | bup newliner

# DESCRIPTION

`bup newliner` is run automatically by bup.  You shouldn't
need it unless you're using it in some other program.

Progress messages emitted by bup (and some other tools) are
of the form "Message ### content\\r", that is, a status
message containing a variable-length number, followed by a
carriage return character and no newline.  If these
messages are printed more than once, they overwrite each
other, so what the user sees is a single line with a
continually-updating number.

This works fine until some other message is printed.  For
example, progress messages are usually printed to stderr,
but other program messages might be printed to stdout.  If
those messages are shorter than the progress message line,
the screen will be left with weird looking artifacts as the
two messages get mixed together.

`bup newliner` prints extra space characters at the right
time to make sure that doesn't happen.

If you're running a program that has problems with these
artifacts, you can usually fix them by piping its stdout
*and* its stderr through bup newliner.

# BUP

Part of the `bup`(1) suite.
