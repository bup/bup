#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

bup() { "$top/bup" "$@"; }

WVPASS "$top/dev/sync-tree" "$top/test/sampledata/" "$tmpdir/src/"

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

WVPASS bup init
WVPASS cd "$tmpdir"

WVSTART "fsck"

WVPASS bup index src
WVPASS bup save -n fsck-test src/b2
WVPASS bup save -n fsck-test src/var/cmd
WVPASS bup save -n fsck-test src/var/doc
WVPASS bup save -n fsck-test src/var/lib
WVPASS bup save -n fsck-test src/y
WVPASS bup fsck
WVPASS bup fsck "$BUP_DIR"/objects/pack/pack-*.pack
WVPASS bup fsck --quick
if bup fsck --par2-ok; then
    WVSTART "fsck (par2)"
else
    WVSTART "fsck (PAR2 IS MISSING)"
fi
WVPASS bup fsck -g
WVPASS bup fsck -r
WVPASS bup damage "$BUP_DIR"/objects/pack/*.pack -n10 -s1 -S0
WVFAIL bup fsck --quick
WVFAIL bup fsck --quick --disable-par2
WVPASS chmod u+w "$BUP_DIR"/objects/pack/*.idx
WVPASS bup damage "$BUP_DIR"/objects/pack/*.idx -n10 -s1 -S0
WVFAIL bup fsck --quick -j4
WVPASS bup damage "$BUP_DIR"/objects/pack/*.pack -n10 -s1024 --percent 0.4 -S0
WVFAIL bup fsck --quick
WVFAIL bup fsck --quick -rvv -j99   # fails because repairs were needed
if bup fsck --par2-ok; then
    WVPASS bup fsck -r # ok because of repairs from last time
    WVPASS bup damage "$BUP_DIR"/objects/pack/*.pack -n202 -s1 --equal -S0
    WVFAIL bup fsck
    WVFAIL bup fsck -rvv   # too many errors to be repairable
    WVFAIL bup fsck -r   # too many errors to be repairable
else
    WVFAIL bup fsck --quick -r # still fails because par2 was missing
fi


WVPASS rm -rf "$tmpdir"
