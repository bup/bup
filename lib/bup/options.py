# Copyright 2010-2012 Avery Pennarun and options.py contributors.
# All rights reserved.
#
# (This license applies to this file but not necessarily the other files in
# this package.)
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#    1. Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#
#    2. Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in
#       the documentation and/or other materials provided with the
#       distribution.
#
# THIS SOFTWARE IS PROVIDED BY AVERY PENNARUN AND CONTRIBUTORS ``AS
# IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL
# <COPYRIGHT HOLDER> OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
# OF THE POSSIBILITY OF SUCH DAMAGE.
#
"""Command-line options parser.
With the help of an options spec string, easily parse command-line options.

An options spec is made up of two parts, separated by a line with two dashes.
The first part is the synopsis of the command and the second one specifies
options, one per line.

Each non-empty line in the synopsis gives a set of options that can be used
together.

Option flags must be at the begining of the line and multiple flags are
separated by commas. Usually, options have a short, one character flag, and a
longer one, but the short one can be omitted.

Long option flags are used as the option's key for the OptDict produced when
parsing options.

When the flag definition is ended with an equal sign, the option takes
one string as an argument, and that string will be converted to an
integer when possible. Otherwise, the option does not take an argument
and corresponds to a boolean flag that is true when the option is
given on the command line.

The option's description is found at the right of its flags definition, after
one or more spaces. The description ends at the end of the line. If the
description contains text enclosed in square brackets, the enclosed text will
be used as the option's default value.

Options can be put in different groups. Options in the same group must be on
consecutive lines. Groups are formed by inserting a line that begins with a
space. The text on that line will be output after an empty line.
"""

from __future__ import absolute_import
import sys, os, textwrap, getopt, re, struct

try:
    import fcntl
except ImportError:
    fcntl = None

try:
    import termios
except ImportError:
    termios = None


def _invert(v, invert):
    if invert:
        return not v
    return v


def _remove_negative_kv(k, v):
    if k.startswith('no-') or k.startswith('no_'):
        return k[3:], not v
    return k,v


class OptDict(object):
    """Dictionary that exposes keys as attributes.

    Keys can be set or accessed with a "no-" or "no_" prefix to negate the
    value.
    """
    def __init__(self, aliases):
        self._opts = {}
        self._aliases = aliases

    def _unalias(self, k):
        k, reinvert = _remove_negative_kv(k, False)
        k, invert = self._aliases[k]
        return k, invert ^ reinvert

    def __setitem__(self, k, v):
        k, invert = self._unalias(k)
        self._opts[k] = _invert(v, invert)

    def __getitem__(self, k):
        k, invert = self._unalias(k)
        return _invert(self._opts[k], invert)

    def __getattr__(self, k):
        return self[k]


def _default_onabort(msg):
    sys.exit(97)


def _intify(v):
    try:
        vv = int(v or '')
        if str(vv) == v:
            return vv
    except ValueError:
        pass
    return v


if not fcntl and termios:
    def _tty_width():
        return 70
else:
    def _tty_width():
        forced = os.environ.get('BUP_TTY_WIDTH', None)
        if forced:
            return int(forced)
        s = struct.pack("HHHH", 0, 0, 0, 0)
        try:
            s = fcntl.ioctl(sys.stderr.fileno(), termios.TIOCGWINSZ, s)
        except IOError:
            return 70
        ysize, xsize, ypix, xpix = struct.unpack('HHHH', s)
        return xsize or 70


class Options:
    """Option parser.
    When constructed, a string called an option spec must be given. It
    specifies the synopsis and option flags and their description.  For more
    information about option specs, see the docstring at the top of this file.

    Two optional arguments specify an alternative parsing function and an
    alternative behaviour on abort (after having output the usage string).

    By default, the parser function is getopt.gnu_getopt, and the abort
    behaviour is to exit the program.
    """
    def __init__(self, optspec, optfunc=getopt.gnu_getopt,
                 onabort=_default_onabort):
        self.optspec = optspec
        self._onabort = onabort
        self.optfunc = optfunc
        self._aliases = {}
        self._shortopts = 'h?'
        self._longopts = ['help', 'usage']
        self._hasparms = {}
        self._defaults = {}
        self._usagestr = self._gen_usage()  # this also parses the optspec

    def _gen_usage(self):
        out = []
        lines = self.optspec.strip().split('\n')
        lines.reverse()
        first_syn = True
        while lines:
            l = lines.pop()
            if l == '--': break
            out.append('%s: %s\n' % (first_syn and 'usage' or '   or', l))
            first_syn = False
        out.append('\n')
        last_was_option = False
        while lines:
            l = lines.pop()
            if l.startswith(' '):
                out.append('%s%s\n' % (last_was_option and '\n' or '',
                                       l.lstrip()))
                last_was_option = False
            elif l:
                (flags,extra) = (l + ' ').split(' ', 1)
                extra = extra.strip()
                if flags.endswith('='):
                    flags = flags[:-1]
                    has_parm = 1
                else:
                    has_parm = 0
                g = re.search(r'\[([^\]]*)\]$', extra)
                if g:
                    defval = _intify(g.group(1))
                else:
                    defval = None
                flagl = flags.split(',')
                flagl_nice = []
                flag_main, invert_main = _remove_negative_kv(flagl[0], False)
                self._defaults[flag_main] = _invert(defval, invert_main)
                for _f in flagl:
                    f,invert = _remove_negative_kv(_f, 0)
                    self._aliases[f] = (flag_main, invert_main ^ invert)
                    self._hasparms[f] = has_parm
                    if f == '#':
                        self._shortopts += '0123456789'
                        flagl_nice.append('-#')
                    elif len(f) == 1:
                        self._shortopts += f + (has_parm and ':' or '')
                        flagl_nice.append('-' + f)
                    else:
                        f_nice = re.sub(r'\W', '_', f)
                        self._aliases[f_nice] = (flag_main,
                                                 invert_main ^ invert)
                        self._longopts.append(f + (has_parm and '=' or ''))
                        self._longopts.append('no-' + f)
                        flagl_nice.append('--' + _f)
                flags_nice = ', '.join(flagl_nice)
                if has_parm:
                    flags_nice += ' ...'
                prefix = '    %-20s  ' % flags_nice
                argtext = '\n'.join(textwrap.wrap(extra, width=_tty_width(),
                                                initial_indent=prefix,
                                                subsequent_indent=' '*28))
                out.append(argtext + '\n')
                last_was_option = True
            else:
                out.append('\n')
                last_was_option = False
        return ''.join(out).rstrip() + '\n'

    def usage(self, msg=""):
        """Print usage string to stderr and abort."""
        sys.stderr.write(self._usagestr)
        if msg:
            sys.stderr.write(msg)
        e = self._onabort and self._onabort(msg) or None
        if e:
            raise e

    def fatal(self, msg):
        """Print an error message to stderr and abort with usage string."""
        msg = '\nerror: %s\n' % msg
        return self.usage(msg)

    def parse(self, args):
        """Parse a list of arguments and return (options, flags, extra).

        In the returned tuple, "options" is an OptDict with known options,
        "flags" is a list of option flags that were used on the command-line,
        and "extra" is a list of positional arguments.
        """
        try:
            (flags,extra) = self.optfunc(args, self._shortopts, self._longopts)
        except getopt.GetoptError as e:
            self.fatal(e)

        opt = OptDict(aliases=self._aliases)

        for k,v in self._defaults.items():
            opt[k] = v

        for (k,v) in flags:
            k = k.lstrip('-')
            if k in ('h', '?', 'help', 'usage'):
                self.usage()
            if (self._aliases.get('#') and
                  k in ('0','1','2','3','4','5','6','7','8','9')):
                v = int(k)  # guaranteed to be exactly one digit
                k, invert = self._aliases['#']
                opt['#'] = v
            else:
                k, invert = opt._unalias(k)
                if not self._hasparms[k]:
                    assert(v == '')
                    v = (opt._opts.get(k) or 0) + 1
                else:
                    v = _intify(v)
            opt[k] = _invert(v, invert)
        return (opt,flags,extra)

    def parse_bytes(self, args):
        if sys.version_info[0] > 2:
            args = [x.decode(errors='surrogateescape') for x in args]
        return self.parse(args)
