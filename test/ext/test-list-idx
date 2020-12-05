#!/usr/bin/env bash
. wvtest-bup.sh || exit $?
. dev/lib.sh || exit $?

set -o pipefail

TOP="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?
export BUP_DIR="$tmpdir/bup"

bup()
{
    "$TOP/bup" "$@"
}

WVSTART 'bup list-idx'

WVPASS bup init
WVPASS cd "$tmpdir"
WVPASS mkdir src
WVPASS bup random 1k > src/data
WVPASS bup index src
WVPASS bup save -n src src
WVPASS bup list-idx "$BUP_DIR"/objects/pack/*.idx
hash1="$(WVPASS bup list-idx "$BUP_DIR"/objects/pack/*.idx)" || exit $?
hash1="${hash1##* }"
WVPASS bup list-idx --find "${hash1}" "$BUP_DIR"/objects/pack/*.idx \
       > list-idx.log || exit $?
found="$(cat list-idx.log)" || exit $?
found="${found##* }"
WVPASSEQ "$found" "$hash1"
WVPASSEQ "$(wc -l < list-idx.log | tr -d ' ')" 1

WVPASS rm -r "$tmpdir"
