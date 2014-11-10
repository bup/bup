#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

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
WVPASS echo content > src/foo
WVPASS chmod 644 src/foo
WVPASS touch -t 201111111111 src/foo
# FUSE, python-fuse, something, can't handle negative epoch times.
# Use pre-epoch to make sure bup properly "bottoms out" at 0 for now.
WVPASS echo content > src/pre-epoch
WVPASS chmod 644 src/pre-epoch
WVPASS touch -t 196907202018 src/pre-epoch
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
WVPASSEQ "$result" "foo
pre-epoch"

# Right now we don't detect new saves.
WVPASS bup save -n src -d "$savestamp2" --strip src
result=$(WVPASS ls mnt/src) || exit $?
savename="$(WVPASS printf '%(%Y-%m-%d-%H%M%S)T' "$savestamp1")" || exit $?
WVPASSEQ "$result" "$savename1
latest"

WVPASS fusermount -uz mnt

WVSTART "extended metadata"
WVPASS bup fuse --meta mnt
result=$(TZ=UTC LC_ALL=C WVPASS ls -l mnt/src/latest/) || exit $?
readonly user=$(WVPASS id -un) || $?
readonly group=$(WVPASS id -gn) || $?
WVPASSEQ "$result" "total 0
-rw-r--r-- 1 $user $group 8 Nov 11  2011 foo
-rw-r--r-- 1 $user $group 8 Jan  1  1970 pre-epoch"

WVPASS fusermount -uz mnt
WVPASS rm -rf "$tmpdir"
