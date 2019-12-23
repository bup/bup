#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?
. t/lib.sh || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

export TZ=UTC

WVPASS bup init
WVPASS cd "$tmpdir"

WVPASS mkdir src

# minimum needed for splitting in this case (found by manual bisect)
NFILES=58

FILELIST=$(for f in $(seq $NFILES) ; do echo $(printf %04d $f) ; done)

WVPASS pushd src
WVPASS touch $FILELIST
WVPASS popd
WVPASS git config --add --bool bup.treesplit true
WVPASS bup index src
WVPASS bup save -n src -d 242312160 --strip src

WVSTART "check stored"
WVPASSEQ "$(WVPASS bup ls /)" "src"
WVPASSEQ "$(WVPASS bup ls /src/latest/)" "$FILELIST"

WVPASS test "$(git ls-tree --name-only src |grep -v '^\.bupm' | wc -l)" -lt $NFILES
WVPASSEQ "$(git ls-tree --name-only src 1.bupd)" "1.bupd"
# git should be able to list the folder
WVPASSEQ "$(git ls-tree --name-only src 0/0058)" "0/0058"

WVSTART "clean up"
WVPASS rm -rf "$tmpdir"
