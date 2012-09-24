#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

if ! [ "$(type -p duplicity)" != "" ]; then
    # FIXME: add WVSKIP.
    echo "Cannot find duplicity; skipping test)" 1>&2
    exit 0
fi

export PASSPHRASE=bup_duplicity_passphrase
D=duplicity.tmp
WVSTART "import-duplicity"
WVPASS bup init
WVPASS cd "$tmpdir"
WVPASS mkdir duplicity
WVPASS duplicity "$top/Documentation" "file://duplicity"
WVPASS bup tick
WVPASS duplicity "$top/Documentation" "file://duplicity"
WVPASS bup import-duplicity "file://duplicity" import-duplicity
WVPASSEQ "$(bup ls import-duplicity/ | wc -l)" "3"
WVPASSEQ "$(bup ls import-duplicity/latest/ | sort)" "$(ls $top/Documentation | sort)"

WVPASS rm -rf "$tmpdir"
