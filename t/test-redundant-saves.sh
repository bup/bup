#!/usr/bin/env bash

# Test that running save more than once with no other changes produces
# the exact same tree.

# Note: we can't compare the top-level hash (i.e. the output of "save
# -t" because that currently pulls the metadata for unindexed parent
# directories directly from the filesystem, and the relevant atimes
# may change between runs.  So instead we extract the roots of the
# indexed trees for comparison via t/subtree-hash.

. ./wvtest-bup.sh

set -eo pipefail

WVSTART 'all'

top="$(pwd)"
tmpdir="$(wvmktempdir)"
export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$BUP_DIR"

bup() { "$top/bup" "$@"; }

mkdir -p "$tmpdir/src"
mkdir -p "$tmpdir/src/d"
mkdir -p "$tmpdir/src/d/e"
touch "$tmpdir/src/"{f,b,a,d}
touch "$tmpdir/src/d/z"

WVPASS bup init
WVPASS bup index -u "$tmpdir/src"

declare -a indexed_top
IFS=/
indexed_top="${tmpdir##/}"
indexed_top=(${indexed_top%%/})
unset IFS

tree1=$(bup save -t "$tmpdir/src") || WVFAIL
indexed_tree1="$(t/subtree-hash "$tree1" "${indexed_top[@]}" src)"

WVPASSEQ "$(cd "$tmpdir/src" && bup index -m)" ""

tree2=$(bup save -t "$tmpdir/src") || WVFAIL
indexed_tree2="$(t/subtree-hash "$tree2" "${indexed_top[@]}" src)"

WVPASSEQ "$indexed_tree1" "$indexed_tree2"

WVPASSEQ "$(bup index -s / | grep ^D)" ""

tree3=$(bup save -t /) || WVFAIL
indexed_tree3="$(t/subtree-hash "$tree3" "${indexed_top[@]}")"

WVPASSEQ "$indexed_tree3" "$indexed_tree3"

rm -rf "$tmpdir"
