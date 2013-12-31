#!/usr/bin/env bash
. ./wvtest-bup.sh
. t/lib.sh

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVSTART "compression"
WVPASS cd "$tmpdir"

D=compression0.tmp
WVPASS force-delete "$BUP_DIR"
WVPASS bup init
WVPASS mkdir $D
WVPASS bup index "$top/Documentation"
WVPASS bup save -n compression -0 --strip "$top/Documentation"
# Some platforms set -A by default when root, so just use it everywhere.
expected="$(WVPASS ls -A "$top/Documentation" | WVPASS sort)" || exit $?
actual="$(WVPASS bup ls -A compression/latest/ | WVPASS sort)" || exit $?
WVPASSEQ "$actual" "$expected"
compression_0_size=$(WVPASS du -k -s "$BUP_DIR" | WVPASS cut -f1) || exit $?

D=compression9.tmp
WVPASS force-delete "$BUP_DIR"
WVPASS bup init
WVPASS mkdir $D
WVPASS bup index "$top/Documentation"
WVPASS bup save -n compression -9 --strip "$top/Documentation"
expected="$(ls -A "$top/Documentation" | sort)" || exit $?
actual="$(bup ls -A compression/latest/ | sort)" || exit $?
WVPASSEQ "$actual" "$expected"
compression_9_size=$(WVPASS du -k -s "$BUP_DIR" | WVPASS cut -f1) || exit $?

WVPASS [ "$compression_9_size" -lt "$compression_0_size" ]


WVPASS rm -rf "$tmpdir"
