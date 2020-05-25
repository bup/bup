#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?
. ./t/lib.sh || exit $?

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
WVPASS bup on - save -ctn src src > get.log
WVPASSEQ $(WVPASS cat get.log | WVPASS wc -l) 2
tree_id=$(WVPASS awk 'FNR == 1' get.log) || exit $?
commit_id=$(WVPASS awk 'FNR == 2' get.log) || exit $?
WVPASS git ls-tree "$tree_id"
WVPASS git cat-file commit "$commit_id" | head -n 1 \
    | WVPASS grep "^tree $tree_id\$"

WVPASS bup restore -C restore "src/latest/$(pwd)/src/."
WVPASS compare-trees src/ restore/
WVPASS rm -r restore

WVSTART "split"
WVPASS bup on - split -ctn baz src/baz > get.log
tree_id=$(WVPASS awk 'FNR == 1' get.log) || exit $?
commit_id=$(WVPASS awk 'FNR == 2' get.log) || exit $?
WVPASS git ls-tree "$tree_id"
WVPASS git cat-file commit "$commit_id" | head -n 1 \
    | WVPASS grep "^tree $tree_id\$"
WVPASS bup join baz > restore-baz
WVPASS cmp src/baz restore-baz

WVSTART "index-cache"
# the 'a-zA-Z0-9_' is '\w' from python,
# the trailing _ is because there's no dir specified
# and that should thus be empty
hostname=$(uname -n)
idxcache=$(echo "$hostname" | sed 's/[^@a-zA-Z0-9_]/_/g')_
# there should be an index-cache now
for idx in "$tmpdir"/bup/objects/pack/*.idx ; do
    cachedidx="$tmpdir/bup/index-cache/$idxcache/$(basename "$idx")"
    WVPASS cmp "$idx" "$cachedidx"
done

WVPASS rm -rf "$tmpdir"
