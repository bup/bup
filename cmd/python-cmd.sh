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

bup_libdir="$script_home/../lib"  # bup_libdir will be adjusted during install

export PYTHONPATH="$bup_libdir${PYTHONPATH:+:$PYTHONPATH}"
export BUP_RESOURCE_PATH="$bup_libdir"

# This last line will be replaced with 'exec some/python "$@"
