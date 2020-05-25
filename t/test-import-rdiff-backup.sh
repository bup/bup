#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

if ! [ "$(type -p rdiff-backup)" != "" ]; then
    # FIXME: add WVSKIP.
    echo "Cannot find rdiff-backup; skipping test)" 1>&2
    exit 0
fi

D=rdiff-backup.tmp
WVSTART "import-rdiff-backup"
WVPASS bup init
WVPASS cd "$tmpdir"
WVPASS mkdir rdiff-backup
WVPASS rdiff-backup "$top/lib/cmd" rdiff-backup
WVPASS bup tick
WVPASS rdiff-backup "$top/Documentation" rdiff-backup
WVPASS bup import-rdiff-backup rdiff-backup import-rdiff-backup
WVPASSEQ $(bup ls import-rdiff-backup/ | wc -l) 3
WVPASSEQ "$(bup ls -A import-rdiff-backup/latest/ | sort)" \
    "$(ls -A "$top/Documentation" | sort)"

WVPASS rm -rf "$tmpdir"
