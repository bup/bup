#!/usr/bin/env bash
. ./wvtest-bup.sh

set -e -o pipefail

WVSTART 'all'

top="$(pwd)"
tmpdir="$(wvmktempdir)"
export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

touch "$tmpdir/foo"
WVPASS bup init
WVPASS bup index "$tmpdir/foo"
WVPASS bup save -n foo "$tmpdir/foo"
WVPASS bup tick
WVPASS bup restore -C "$tmpdir/restore" "foo/latest/$tmpdir/foo"
WVPASS "$top/t/compare-trees" "$tmpdir/foo" "$tmpdir/restore/foo"

rm -rf "$tmpdir"
