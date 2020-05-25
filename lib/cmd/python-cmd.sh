#!/bin/sh

set -e

top="$(pwd)"
cmdpath="$0"
# loop because macos has no recursive resolution
while test -L "$cmdpath"; do
    link="$(readlink "$cmdpath")"
    cd "$(dirname "$cmdpath")"
    cmdpath="$link"
done
script_home="$(cd "$(dirname "$cmdpath")" && pwd -P)"
cd "$top"

bup_libdir="$script_home/.."  # bup_libdir will be adjusted during install
export PYTHONPATH="$bup_libdir${PYTHONPATH:+:$PYTHONPATH}"

# Force python to use ISO-8859-1 (aka Latin 1), a single-byte
# encoding, to help avoid any manipulation of data from system APIs
# (paths, users, groups, command line arguments, etc.)

export PYTHONCOERCECLOCALE=0  # Perhaps not necessary, but shouldn't hurt

# We can't just export LC_CTYPE directly here because the locale might
# not exist outside python, and then bash (at least) may be cranky.

if [ "${LC_ALL+x}" ]; then
    unset LC_ALL
    exec env \
         BUP_LC_ALL="$LC_ALL" \
         LC_COLLATE="$LC_ALL" \
         LC_MONETARY="$LC_ALL" \
         LC_NUMERIC="$LC_ALL" \
         LC_TIME="$LC_ALL" \
         LC_MESSAGES="$LC_ALL" \
         LC_CTYPE=ISO-8859-1 \
         @bup_python@ "$@"
elif [ "${LC_CTYPE+x}" ]; then
    exec env \
         BUP_LC_CTYPE="$LC_CTYPE" \
         LC_CTYPE=ISO-8859-1 \
         @bup_python@ "$@"
else
    exec env \
         LC_CTYPE=ISO-8859-1 \
         @bup_python@ "$@"
fi
