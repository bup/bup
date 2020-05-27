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

WVSTART 'main'

bup
rc=$?
WVPASSEQ "$rc" 99

WVPASS rm -r "$tmpdir"
