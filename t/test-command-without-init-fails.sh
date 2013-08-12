#!/usr/bin/env bash
. ./wvtest-bup.sh

set -e -o pipefail

WVSTART 'all'

top="$(pwd)"
tmpdir="$(wvmktempdir)"
export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

mkdir "$tmpdir/foo"

set +e
bup index "$tmpdir/foo" &> /dev/null
index_rc=$?
set -e
WVPASSEQ "$index_rc" "15"

rm -rf "$tmpdir"
