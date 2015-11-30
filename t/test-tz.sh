#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVSTART "half hour TZ"

export TZ=ACDT-10:30

WVPASS bup init
WVPASS cd "$tmpdir"

WVPASS mkdir src
WVPASS bup index src
WVPASS bup save -n src -d 1420164180 src

WVPASSEQ "$(WVPASS git cat-file commit src | sed -ne 's/^author .*> //p')" \
"1420164180 +1030"

WVPASSEQ "$(WVPASS bup ls /src)" \
"2015-01-02-123300
latest"

WVPASS rm -rf "$tmpdir"
