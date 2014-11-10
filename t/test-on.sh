#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $? || exit $?
. ./t/lib.sh || exit $? || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }
compare-trees() { "$top/t/compare-trees" "$@"; }

WVPASS bup init
WVPASS cd "$tmpdir"

WVSTART "index/save"
WVPASS mkdir src src/foo
WVPASS date > src/bar
WVPASS bup random 1k > src/baz
WVPASS bup on - index src
WVPASS bup on - save -n src src
WVPASS bup restore -C restore "src/latest/$(pwd)/src/."
WVPASS compare-trees src/ restore/
WVPASS rm -r restore

WVSTART "split"
WVPASS bup on - split -n baz src/baz
WVPASS bup join baz > restore-baz
WVPASS cmp src/baz restore-baz

WVPASS rm -rf "$tmpdir"
