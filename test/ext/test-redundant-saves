#!/usr/bin/env bash

# Test that running save more than once with no other changes produces
# the exact same tree.

# Note: we can't compare the top-level hash (i.e. the output of "save
# -t" because that currently pulls the metadata for unindexed parent
# directories directly from the filesystem, and the relevant atimes
# may change between runs.  So instead we extract the roots of the
# indexed trees for comparison via dev/subtree-hash.

. ./wvtest-bup.sh || exit $?

set -o pipefail

WVSTART 'all'

top="$(pwd)"
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$BUP_DIR"

bup() { "$top/bup" "$@"; }

WVPASS mkdir -p "$tmpdir/src"
WVPASS mkdir -p "$tmpdir/src/d"
WVPASS mkdir -p "$tmpdir/src/d/e"
WVPASS touch "$tmpdir/src/"{f,b,a,d}
WVPASS touch "$tmpdir/src/d/z"

WVPASS bup init
WVPASS bup index -u "$tmpdir/src"

declare -a indexed_top
IFS=/
indexed_top="${tmpdir##/}"
indexed_top=(${indexed_top%%/})
unset IFS

tree1=$(WVPASS bup save -t "$tmpdir/src") || exit $?
indexed_tree1="$(WVPASS dev/subtree-hash "$tree1" "${indexed_top[@]}" src)" \
    || exit $?

result="$(WVPASS cd "$tmpdir/src"; WVPASS bup index -m)" || exit $?
WVPASSEQ "$result" ""

tree2=$(WVPASS bup save -t "$tmpdir/src") || exit $?
indexed_tree2="$(WVPASS dev/subtree-hash "$tree2" "${indexed_top[@]}" src)" \
    || exit $?

WVPASSEQ "$indexed_tree1" "$indexed_tree2"

result="$(WVPASS bup index -s / | WVFAIL grep ^D)" || exit $?
WVPASSEQ "$result" ""

tree3=$(WVPASS bup save -t /) || exit $?
indexed_tree3="$(WVPASS dev/subtree-hash "$tree3" "${indexed_top[@]}" src)" || exit $?
WVPASSEQ "$indexed_tree1" "$indexed_tree3"

WVPASS rm -rf "$tmpdir"
