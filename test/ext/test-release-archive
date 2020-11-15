#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?
. dev/lib.sh || exit $?

set -o pipefail

bup_make=$(< config/config.var/bup-make)

WVPASS git status > /dev/null

if ! git diff-index --quiet HEAD; then
    WVDIE "uncommitted changes; cannot continue"
fi

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

bup() { "$top/bup" "$@"; }

WVPASS cd "$tmpdir"

WVPASS git clone "$top" clone

for ver in 11.11 11.11.11; do
    WVSTART "version $ver"
    WVPASS cd clone
    WVPASS git tag "$ver"
    WVPASS git archive --prefix=bup-"$ver"/ -o "$tmpdir"/bup-"$ver".tgz "$ver"
    WVPASS cd "$tmpdir"
    WVPASS tar xzf bup-"$ver".tgz
    WVPASS cd bup-"$ver"
    WVPASS "$bup_make"
    WVPASSEQ "$ver" "$(./bup version)"
    WVPASS cd "$tmpdir"
done

WVSTART 'make check in unpacked archive'
WVPASS cd bup-11.11.11
if ! "$bup_make" -j5 check > archive-tests.log 2>&1; then
    cat archive-tests.log 1>&2
    WVPASS false
fi

WVPASS cd "$top"
WVPASS rm -rf "$tmpdir"
