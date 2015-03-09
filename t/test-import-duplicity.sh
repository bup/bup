#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

set -o pipefail

if ! [ "$(type -p duplicity)" != "" ]; then
    # FIXME: add WVSKIP.
    echo "Cannot find duplicity; skipping test)" 1>&2
    exit 0
fi

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

bup() { "$top/bup" "$@"; }
dup() { duplicity --archive-dir "$tmpdir/dup-cache" "$@"; }

WVSTART "import-duplicity"
WVPASS make install DESTDIR="$tmpdir/src"

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"
export PASSPHRASE=bup_duplicity_passphrase

WVPASS bup init
WVPASS cd "$tmpdir"
WVPASS mkdir duplicity
WVPASS dup src file://duplicity
WVPASS bup tick
WVPASS touch src/new-file
WVPASS dup src file://duplicity
WVPASS bup import-duplicity "file://duplicity" import-duplicity
WVPASSEQ "$(bup ls import-duplicity/ | wc -l)" "3"
WVPASSEQ "$(bup ls import-duplicity/latest/ | sort)" "$(ls src | sort)"
WVPASS bup restore -C restore/ import-duplicity/latest/
WVFAIL "$top/t/compare-trees" src/ restore/ > tmp-compare-trees
WVPASSEQ $(cat tmp-compare-trees | wc -l) 1
# Note: OS X rsync itemize output is currently only 9 chars, not 11.
expected_diff_rx='^\.d\.\.t.\.\.\.\.?\.? \./$'
if ! grep -qE "$expected_diff_rx" tmp-compare-trees; then
    echo -n 'tmp-compare-trees: ' 1>&2
    cat tmp-compare-trees 1>&2
fi
WVPASS grep -qE "$expected_diff_rx" tmp-compare-trees

WVPASS rm -rf "$tmpdir"
