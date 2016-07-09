#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?
. t/lib.sh || exit $?

set -o pipefail

unset BLOCKSIZE BLOCK_SIZE DF_BLOCK_SIZE

if ! bup-python -c 'import fuse' 2> /dev/null; then
    WVSTART 'unable to import fuse; skipping test'
    exit 0
fi

if test -n "$(type -p modprobe)" && ! modprobe fuse; then
    echo 'Unable to load fuse module; skipping dependent tests.' 1>&2
    exit 0
fi

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

# Some versions of bash's printf don't support the relevant date expansion.
savename()
{
    readonly secs="$1"
    WVPASS bup-python -c "from time import strftime, localtime; \
       print strftime('%Y-%m-%d-%H%M%S', localtime($secs))"
}

WVPASS bup init
WVPASS cd "$tmpdir"

savestamp1=$(WVPASS bup-python -c 'import time; print int(time.time())') || exit $?
savestamp2=$(($savestamp1 + 1))

savename1="$(savename "$savestamp1")" || exit $?
savename2="$(savename "$savestamp2")" || exit $?

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

result=$(WVPASS cat mnt/src/latest/foo) || exit $?
WVPASSEQ "$result" "content"

# Right now we don't detect new saves.
WVPASS bup save -n src -d "$savestamp2" --strip src
result=$(WVPASS ls mnt/src) || exit $?
WVPASSEQ "$result" "$savename1
latest"

WVPASS fusermount -uz mnt

WVSTART "extended metadata"
WVPASS bup fuse --meta mnt
result=$(TZ=UTC LC_ALL=C WVPASS ls -l mnt/src/latest/) || exit $?
readonly user=$(WVPASS id -un) || $?
readonly group=$(WVPASS id -gn) || $?
WVPASSEQ "$result" "total 1
-rw-r--r-- 1 $user $group 8 Nov 11  2011 foo
-rw-r--r-- 1 $user $group 8 Jan  1  1970 pre-epoch"

WVPASS fusermount -uz mnt
WVPASS rm -rf "$tmpdir"
