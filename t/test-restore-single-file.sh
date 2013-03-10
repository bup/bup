#!/usr/bin/env bash
. ./wvtest-bup.sh

set -e -o pipefail

WVSTART 'all'

top="$(pwd)"
tmpdir="$(wvmktempdir)"
export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

mkdir "$tmpdir/foo"
mkdir "$tmpdir/foo/bar" # Make sure a dir sorts before baz (regression test).
touch "$tmpdir/foo/baz"
WVPASS bup init
WVPASS bup index "$tmpdir/foo"
WVPASS bup save -n foo "$tmpdir/foo"
# Make sure the timestamps will differ if metadata isn't being restored.
WVPASS bup tick
WVPASS bup restore -C "$tmpdir/restore" "foo/latest/$tmpdir/foo/baz"
WVPASS "$top/t/compare-trees" "$tmpdir/foo/baz" "$tmpdir/restore/baz"

rm -rf "$tmpdir"
