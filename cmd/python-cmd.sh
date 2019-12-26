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

# Force python to use ISO-8859-1 (aka Latin 1), a single-byte
# encoding, to help avoid any manipulation of data from system APIs
# (paths, users, groups, command line arguments, etc.)

# Preserve for selective use
if [ "${LC_CTYPE+x}" ]; then export BUP_LC_CTYPE="$LC_CTYPE"; fi
if [ "${LC_ALL+x}" ]; then
    export BUP_LC_ALL="$LC_ALL"
    export LC_COLLATE="$LC_ALL"
    export LC_MONETARY="$LC_ALL"
    export LC_NUMERIC="$LC_ALL"
    export LC_TIME="$LC_ALL"
    export LC_MESSAGES="$LC_ALL"
    unset LC_ALL
fi

export PYTHONCOERCECLOCALE=0  # Perhaps not necessary, but shouldn't hurt
export LC_CTYPE=ISO-8859-1

bup_libdir="$script_home/../lib"  # bup_libdir will be adjusted during install

export PYTHONPATH="$bup_libdir${PYTHONPATH:+:$PYTHONPATH}"

exec @bup_python@ "$@"
