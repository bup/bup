#!/usr/bin/env bash
. ./wvtest-bup.sh

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

GC_OPTS=--unsafe

bup() { "$top/bup" "$@"; }
compare-trees() { "$top/dev/compare-trees" "$@"; }
data-size() { "$top/dev/data-size" "$@"; }

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

size_before=$(WVPASS data-size "$BUP_DIR") || exit $?
WVPASS rm "$BUP_DIR/refs/heads/src-2"
WVPASS bup gc $GC_OPTS -v
size_after=$(WVPASS data-size "$BUP_DIR") || exit $?

WVPASS [ "$size_before" -gt 5000000 ]
WVPASS [ "$size_after" -lt 50000 ]

WVPASS rm -r "$tmpdir/restore"
WVPASS bup restore -C "$tmpdir/restore" /src-1/latest
WVPASS compare-trees src-1/ "$tmpdir/restore/latest/"

WVPASS rm -r "$tmpdir/restore"
WVFAIL bup restore -C "$tmpdir/restore" /src-2/latest
 

WVPASS mkdir src-ab-clean src-ab-clean/a src-ab-clean/b
WVPASS bup random 1k > src-ab-clean/a/1
WVPASS bup random 10M > src-ab-clean/b/1


WVSTART "gc (rewriting)"

WVPASS rm -rf "$BUP_DIR"
WVPASS bup init
WVPASS rm -rf src-ab
WVPASS cp -pPR src-ab-clean src-ab

WVPASS bup index src-ab
WVPASS bup save --strip -n src-ab src-ab
WVPASS bup index --clear
WVPASS bup index src-ab
WVPASS bup save -vvv --strip -n a src-ab/a

size_before=$(WVPASS data-size "$BUP_DIR") || exit $?
WVPASS rm "$BUP_DIR/refs/heads/src-ab"
WVPASS bup gc $GC_OPTS -v
size_after=$(WVPASS data-size "$BUP_DIR") || exit $?

WVPASS [ "$size_before" -gt 5000000 ]
WVPASS [ "$size_after" -lt 100000 ]

WVPASS rm -r "$tmpdir/restore"
WVPASS bup restore -C "$tmpdir/restore" /a/latest
WVPASS compare-trees src-ab/a/ "$tmpdir/restore/latest/"

WVPASS rm -r "$tmpdir/restore"
WVFAIL bup restore -C "$tmpdir/restore" /src-ab/latest


WVSTART "gc (save -r after repo rewriting)"

WVPASS rm -rf "$BUP_DIR"
WVPASS bup init
WVPASS bup -d bup-remote init
WVPASS rm -rf src-ab
WVPASS cp -pPR src-ab-clean src-ab

WVPASS bup index src-ab
WVPASS bup save -r :bup-remote --strip -n src-ab src-ab
WVPASS bup index --clear
WVPASS bup index src-ab
WVPASS bup save -r :bup-remote -vvv --strip -n a src-ab/a

size_before=$(WVPASS data-size bup-remote) || exit $?
WVPASS rm bup-remote/refs/heads/src-ab
WVPASS bup -d bup-remote gc $GC_OPTS -v
size_after=$(WVPASS data-size bup-remote) || exit $?

WVPASS [ "$size_before" -gt 5000000 ]
WVPASS [ "$size_after" -lt 100000 ]

WVPASS rm -rf "$tmpdir/restore"
WVPASS bup -d bup-remote restore -C "$tmpdir/restore" /a/latest
WVPASS compare-trees src-ab/a/ "$tmpdir/restore/latest/"

WVPASS rm -r "$tmpdir/restore"
WVFAIL bup -d bup-remote restore -C "$tmpdir/restore" /src-ab/latest

# Make sure a post-gc index/save that includes gc-ed data works
WVPASS bup index src-ab
WVPASS bup save -r :bup-remote --strip -n src-ab src-ab
WVPASS rm -r "$tmpdir/restore"
WVPASS bup -d bup-remote restore -C "$tmpdir/restore" /src-ab/latest
WVPASS compare-trees src-ab/ "$tmpdir/restore/latest/"


WVSTART "gc (bup on after repo rewriting)"

WVPASS rm -rf "$BUP_DIR"
WVPASS bup init
WVPASS rm -rf src-ab
WVPASS cp -pPR src-ab-clean src-ab

WVPASS bup on - index src-ab
WVPASS bup on - save --strip -n src-ab src-ab
WVPASS bup index --clear
WVPASS bup on - index src-ab
WVPASS bup on - save -vvv --strip -n a src-ab/a

size_before=$(WVPASS data-size "$BUP_DIR") || exit $?
WVPASS rm "$BUP_DIR/refs/heads/src-ab"
WVPASS bup gc $GC_OPTS -v
size_after=$(WVPASS data-size "$BUP_DIR") || exit $?

WVPASS [ "$size_before" -gt 5000000 ]
WVPASS [ "$size_after" -lt 100000 ]

WVPASS rm -r "$tmpdir/restore"
WVPASS bup restore -C "$tmpdir/restore" /a/latest
WVPASS compare-trees src-ab/a/ "$tmpdir/restore/latest/"

WVPASS rm -r "$tmpdir/restore"
WVFAIL bup restore -C "$tmpdir/restore" /src-ab/latest

# Make sure a post-gc index/save that includes gc-ed data works
WVPASS bup on - index src-ab
WVPASS bup on - save --strip -n src-ab src-ab
WVPASS rm -r "$tmpdir/restore"
WVPASS bup restore -C "$tmpdir/restore" /src-ab/latest
WVPASS compare-trees src-ab/ "$tmpdir/restore/latest/"


WVSTART "gc (threshold)"

WVPASS rm -rf "$BUP_DIR"
WVPASS bup init
WVPASS rm -rf src && mkdir src
WVPASS echo 0 > src/0
WVPASS echo 1 > src/1

WVPASS bup index src
WVPASS bup save -n src-1 src
WVPASS rm src/0
WVPASS bup index src
WVPASS bup save -n src-2 src

WVPASS bup rm --unsafe src-1
packs_before="$(ls "$BUP_DIR/objects/pack/"*.pack)" || exit $?
WVPASS bup gc -v $GC_OPTS --threshold 99 2>&1 | tee gc.log
packs_after="$(ls "$BUP_DIR/objects/pack/"*.pack)" || exit $?
WVPASSEQ 0 "$(grep -cE '^rewriting ' gc.log)"
WVPASSEQ "$packs_before" "$packs_after"

WVPASS bup gc -v $GC_OPTS --threshold 1 2>&1 | tee gc.log
packs_after="$(ls "$BUP_DIR/objects/pack/"*.pack)" || exit $?
WVPASSEQ 1 "$(grep -cE '^rewriting ' gc.log)"

# Check that only one pack was rewritten

# Accommodate some systems that apparently used to change the default
# ls sort order which must match LC_COLLATE for comm to work.
packs_before="$(sort <(echo "$packs_before"))" || die $?
packs_after="$(sort <(echo "$packs_after"))" || die $?

only_in_before="$(comm -2 -3 <(echo "$packs_before") <(echo "$packs_after"))" \
    || die $?

only_in_after="$(comm -1 -3 <(echo "$packs_before") <(echo "$packs_after"))" \
    || die $?

in_both="$(comm -1 -2 <(echo "$packs_before") <(echo "$packs_after"))" || die $?

WVPASSEQ 1 $(echo "$only_in_before" | wc -l)
WVPASSEQ 1 $(echo "$only_in_after" | wc -l)
WVPASSEQ 1 $(echo "$in_both" | wc -l)

WVSTART "gc (threshold 0)"

WVPASS rm -rf "$BUP_DIR"
WVPASS bup init
WVPASS rm -rf src && mkdir src
WVPASS echo 0 > src/0
WVPASS echo 1 > src/1

WVPASS bup index src
WVPASS bup save -n src-1 src

packs_before="$(ls "$BUP_DIR/objects/pack/"*.pack)" || exit $?
WVPASS bup gc -v $GC_OPTS --threshold 0 2>&1 | tee gc.log
packs_after="$(ls "$BUP_DIR/objects/pack/"*.pack)" || exit $?
# Check that the pack was rewritten, but not removed (since the
# result-pack is equal to the source pack)
WVPASSEQ 1 "$(grep -cE '^rewriting ' gc.log)"
WVPASSEQ "$packs_before" "$packs_after"

WVPASS rm -rf "$tmpdir"
