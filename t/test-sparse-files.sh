#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

set -o pipefail

readonly mb=1048576
readonly top="$(WVPASS pwd)" || exit $?
readonly tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS cd "$tmpdir"

WVPASS dd if=/dev/zero of=test-sparse seek=$((1024 * 256)) bs=1 count=1
restore_size=$(WVPASS du -k -s test-sparse | WVPASS cut -f1) || exit $?
if ! [ "$restore_size" -lt 256 ]; then
    WVSTART "no sparse support detected -- skipping tests"
    exit 0
fi

WVPASS bup init
WVPASS mkdir src

WVPASS dd if=/dev/zero of=src/foo seek=$mb bs=1 count=1
WVPASS bup index src
WVPASS bup save -n src src

WVSTART "sparse file restore (all sparse)"
WVPASS bup restore -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -gt 1000 ]
WVPASS "$top/t/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --no-sparse (all sparse)"
WVPASS rm -r restore
WVPASS bup restore --no-sparse -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -gt 1000 ]
WVPASS "$top/t/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (all sparse)"
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -lt 100 ]
WVPASS "$top/t/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (sparse end)"
WVPASS echo "start" > src/foo
WVPASS dd if=/dev/zero of=src/foo seek=$mb bs=1 count=1 conv=notrunc
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -lt 100 ]
WVPASS "$top/t/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (sparse middle)"
WVPASS echo "end" >> src/foo
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -lt 100 ]
WVPASS "$top/t/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (sparse start)"
WVPASS dd if=/dev/zero of=src/foo seek=$mb bs=1 count=1
WVPASS echo "end" >> src/foo
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -lt 100 ]
WVPASS "$top/t/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (sparse start and end)"
WVPASS dd if=/dev/zero of=src/foo seek=$mb bs=1 count=1
WVPASS echo "middle" >> src/foo
WVPASS dd if=/dev/zero of=src/foo seek=$((2 * mb)) bs=1 count=1 conv=notrunc
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -lt 100 ]
WVPASS "$top/t/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (random)"
WVPASS bup random 512k > src/foo
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
WVPASS "$top/t/compare-trees" -c src/ restore/src/

WVPASS rm -rf "$tmpdir"
