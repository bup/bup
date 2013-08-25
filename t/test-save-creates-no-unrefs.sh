#!/usr/bin/env bash
. ./wvtest-bup.sh

set -eo pipefail

WVSTART 'all'

top="$(pwd)"
tmpdir="$(wvmktempdir)"
export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$BUP_DIR"

bup() { "$top/bup" "$@"; }

mkdir -p "$tmpdir/src"
touch "$tmpdir/src/foo"
bup init
bup index "$tmpdir/src"
bup save -n src "$tmpdir/src"
WVPASSEQ "$(git fsck --unreachable)" ""
bup save -n src "$tmpdir/src"
WVPASSEQ "$(git fsck --unreachable)" ""

rm -rf "$tmpdir"
