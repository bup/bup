#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

set -o pipefail

WVSTART 'all'

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?
export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS mkdir "$tmpdir/foo"
WVPASS mkdir "$tmpdir/foo/bar" # Make sure a dir sorts before baz (regression test).
WVPASS touch "$tmpdir/foo/baz"
WVPASS WVPASS bup init
WVPASS WVPASS bup index "$tmpdir/foo"
WVPASS bup save -n foo "$tmpdir/foo"
# Make sure the timestamps will differ if metadata isn't being restored.
WVPASS bup tick
WVPASS bup restore -C "$tmpdir/restore" "foo/latest/$tmpdir/foo/baz"
WVPASS "$top/dev/compare-trees" "$tmpdir/foo/baz" "$tmpdir/restore/baz"

WVPASS rm -rf "$tmpdir"

