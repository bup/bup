#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

WVSTART 'all'

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?
export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$BUP_DIR"

bup() { "$top/bup" "$@"; }

WVPASS mkdir -p "$tmpdir/src"
WVPASS touch "$tmpdir/src/foo"
WVPASS bup init
WVPASS bup index "$tmpdir/src"
WVPASS bup save -n src "$tmpdir/src"
WVPASSEQ "$(git fsck --unreachable)" ""
WVPASS bup save -n src "$tmpdir/src"
WVPASSEQ "$(git fsck --unreachable)" ""

WVPASS rm -rf "$tmpdir"
