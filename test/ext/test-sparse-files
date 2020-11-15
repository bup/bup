#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?
. dev/lib.sh || exit $?

set -o pipefail

mb=1048576
top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?
readonly mb top tmpdir

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS cd "$tmpdir"

# The 3MB guess is semi-arbitrary, but we've been informed that
# Lustre, for example, uses 1MB, so guess higher than that, at least.
block_size=$(bup-cfg-py -c \
  "import os; print(getattr(os.stat('.'), 'st_blksize', 0)) or $mb * 3") \
    || exit $?
data_size=$((block_size * 10))
readonly block_size data_size

WVPASS dd if=/dev/zero of=test-sparse-probe seek="$data_size" bs=1 count=1
probe_size=$(WVPASS du -k -s test-sparse-probe | WVPASS cut -f1) || exit $?
if [ "$probe_size" -ge "$((data_size / 1024))" ]; then
    WVSTART "no sparse support detected -- skipping tests"
    exit 0
fi

WVSTART "sparse restore on $(current-filesystem), assuming ${block_size}B blocks"

WVPASS bup init
WVPASS mkdir src

WVPASS dd if=/dev/zero of=src/foo seek="$data_size" bs=1 count=1
WVPASS bup index src
WVPASS bup save -n src src

WVSTART "sparse file restore (all sparse)"
WVPASS bup restore -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore/src/foo | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -ge "$((data_size / 1024))" ]
WVPASS "$top/dev/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --no-sparse (all sparse)"
WVPASS rm -r restore
WVPASS bup restore --no-sparse -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore/src/foo | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -ge "$((data_size / 1024))" ]
WVPASS "$top/dev/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (all sparse)"
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore/src/foo | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -le "$((3 * (block_size / 1024)))" ]
WVPASS "$top/dev/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (sparse end)"
WVPASS echo "start" > src/foo
WVPASS dd if=/dev/zero of=src/foo seek="$data_size" bs=1 count=1 conv=notrunc
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore/src/foo | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -le "$((3 * (block_size / 1024)))" ]
WVPASS "$top/dev/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (sparse middle)"
WVPASS echo "end" >> src/foo
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore/src/foo | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -le "$((5 * (block_size / 1024)))" ]
WVPASS "$top/dev/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (bracketed zero run in buf)"
WVPASS echo 'x' > src/foo
WVPASS dd if=/dev/zero bs=1 count=512 >> src/foo
WVPASS echo 'y' >> src/foo
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
WVPASS "$top/dev/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (sparse start)"
WVPASS dd if=/dev/zero of=src/foo seek="$data_size" bs=1 count=1
WVPASS echo "end" >> src/foo
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore/src/foo | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -le "$((5 * (block_size / 1024)))" ]
WVPASS "$top/dev/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (sparse start and end)"
WVPASS dd if=/dev/zero of=src/foo seek="$data_size" bs=1 count=1
WVPASS echo "middle" >> src/foo
WVPASS dd if=/dev/zero of=src/foo seek=$((2 * data_size)) bs=1 count=1 conv=notrunc
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
restore_size=$(WVPASS du -k -s restore/src/foo | WVPASS cut -f1) || exit $?
WVPASS [ "$restore_size" -le "$((5 * (block_size / 1024)))" ]
WVPASS "$top/dev/compare-trees" -c src/ restore/src/

if test "$block_size" -gt $mb; then
    random_size="$block_size"
else
    random_size=1M
fi
WVSTART "sparse file restore --sparse (random $random_size)"
WVPASS bup random --seed "$RANDOM" 1M > src/foo
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
WVPASS "$top/dev/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (random sparse regions)"
WVPASS rm -rf "$BUP_DIR" src
WVPASS bup init
WVPASS mkdir src
for sparse_dataset in 0 1 2 3 4 5 6 7 8 9
do
    WVPASS "$top/dev/sparse-test-data" "src/foo-$sparse_dataset"
done
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
WVPASS "$top/dev/compare-trees" -c src/ restore/src/

WVSTART "sparse file restore --sparse (short zero runs around boundary)"
WVPASS bup-cfg-py > src/foo <<EOF
from sys import stdout
stdout.write("x" * 65535 + "\0")
stdout.write("\0" + "x" * 65535)
stdout.write("\0" + "x" * 65534 + "\0")
stdout.write("x" * 65536)
stdout.write("\0")
EOF
WVPASS bup index src
WVPASS bup save -n src src
WVPASS rm -r restore
WVPASS bup restore --sparse -C restore "src/latest/$(pwd)/"
WVPASS "$top/dev/compare-trees" -c src/ restore/src/


WVPASS rm -rf "$tmpdir"
