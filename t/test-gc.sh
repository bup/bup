#!/usr/bin/env bash
. ./wvtest-bup.sh

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

GC_OPTS=--unsafe

bup() { "$top/bup" "$@"; }
compare-trees() { "$top/t/compare-trees" "$@"; }

WVPASS cd "$tmpdir"
WVPASS bup init

WVSTART "gc (unchanged repo)"

WVPASS mkdir src-1
WVPASS bup random 1k > src-1/1
WVPASS bup index src-1
WVPASS bup save --strip -n src-1 src-1

WVPASS bup gc $GC_OPTS -v

WVPASS bup restore -C "$tmpdir/restore" /src-1/latest
WVPASS compare-trees src-1/ "$tmpdir/restore/latest/"

WVSTART "gc (unchanged, new branch)"

WVPASS mkdir src-2
WVPASS bup random 10M > src-2/1
WVPASS bup index src-2
WVPASS bup save --strip -n src-2 src-2

WVPASS bup gc $GC_OPTS -v

WVPASS rm -r "$tmpdir/restore"
WVPASS bup restore -C "$tmpdir/restore" /src-1/latest
WVPASS compare-trees src-1/ "$tmpdir/restore/latest/"

WVPASS rm -r "$tmpdir/restore"
WVPASS bup restore -C "$tmpdir/restore" /src-2/latest
WVPASS compare-trees src-2/ "$tmpdir/restore/latest/"

WVSTART "gc (removed branch)"

size_before=$(WVPASS du -k -s "$BUP_DIR" | WVPASS cut -f1) || exit $?
WVPASS rm "$BUP_DIR/refs/heads/src-2"
WVPASS bup gc $GC_OPTS -v
size_after=$(WVPASS du -k -s "$BUP_DIR" | WVPASS cut -f1) || exit $?

WVPASS [ "$size_before" -gt 5000 ]
WVPASS [ "$size_after" -lt 500 ]

WVPASS rm -r "$tmpdir/restore"
WVPASS bup restore -C "$tmpdir/restore" /src-1/latest
WVPASS compare-trees src-1/ "$tmpdir/restore/latest/"

WVPASS rm -r "$tmpdir/restore"
WVFAIL bup restore -C "$tmpdir/restore" /src-2/latest
 
WVSTART "gc (rewriting)"

WVPASS rm -rf "$BUP_DIR"
WVPASS bup init

WVPASS mkdir src-ab src-ab/a src-ab/b
WVPASS bup random 1k > src-ab/a/1
WVPASS bup random 10M > src-ab/b/1

WVPASS bup index src-ab
WVPASS bup save --strip -n src-ab src-ab
WVPASS bup index --clear
WVPASS bup index src-ab
WVPASS bup save -vvv --strip -n a src-ab/a

size_before=$(WVPASS du -k -s "$BUP_DIR" | WVPASS cut -f1) || exit $?
WVPASS rm "$BUP_DIR/refs/heads/src-ab"
WVPASS bup gc $GC_OPTS -v
size_after=$(WVPASS du -k -s "$BUP_DIR" | WVPASS cut -f1) || exit $?

WVPASS [ "$size_before" -gt 5000 ]
WVPASS [ "$size_after" -lt 500 ]

WVPASS rm -r "$tmpdir/restore"
WVPASS bup restore -C "$tmpdir/restore" /a/latest
WVPASS compare-trees src-ab/a/ "$tmpdir/restore/latest/"

WVPASS rm -r "$tmpdir/restore"
WVFAIL bup restore -C "$tmpdir/restore" /src-ab/latest

WVPASS rm -rf "$tmpdir"
