#!/usr/bin/env bash
. ./wvtest-bup.sh

set -o pipefail

if ! fusermount -V; then
    echo 'skipping FUSE tests: fusermount does not appear to work'
    exit 0
fi

if ! groups | grep -q fuse && test "$(t/root-status)" != root; then
    echo 'skipping FUSE tests: you are not root and not in the fuse group'
    exit 0
fi

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS bup init
WVPASS cd "$tmpdir"

savestamp1=$(WVPASS python -c 'import time; print int(time.time())') || exit $?
savestamp2=$(($savestamp1 + 1))
savename1="$(printf '%(%Y-%m-%d-%H%M%S)T' "$savestamp1")" || exit $?
savename2="$(printf '%(%Y-%m-%d-%H%M%S)T' "$savestamp2")" || exit $?

WVPASS mkdir src
WVPASS date > src/foo
WVPASS bup index src
WVPASS bup save -n src -d "$savestamp1" --strip src

WVSTART "basics"
WVPASS mkdir mnt
WVPASS bup fuse mnt

result=$(WVPASS ls mnt) || exit $?
WVPASSEQ src "$result"

result=$(WVPASS ls mnt/src) || exit $?
WVPASSEQ "$result" "$savename1
latest"

result=$(WVPASS ls mnt/src/latest) || exit $?
WVPASSEQ "$result" "foo"

# Right now we don't detect new saves.
WVPASS bup save -n src -d "$savestamp2" --strip src
result=$(WVPASS ls mnt/src) || exit $?
savename="$(WVPASS printf '%(%Y-%m-%d-%H%M%S)T' "$savestamp1")" || exit $?
WVPASSEQ "$result" "$savename1
latest"

WVPASS fusermount -uz mnt
WVPASS rm -rf "$tmpdir"
