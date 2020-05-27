#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }


WVPASS bup init
WVPASS cd "$tmpdir"


WVSTART "index --clear"
WVPASS mkdir src
WVPASS touch src/foo src/bar
WVPASS bup index -u src
WVPASSEQ "$(bup index -p)" "src/foo
src/bar
src/
./"
WVPASS rm src/foo
WVPASS bup index --clear
WVPASS bup index -u src
expected="$(WVPASS bup index -p)" || exit $?
WVPASSEQ "$expected" "src/bar
src/
./"


WVPASS rm -rf "$tmpdir"
