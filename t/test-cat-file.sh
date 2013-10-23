#!/usr/bin/env bash
. ./wvtest-bup.sh

set -eo pipefail

top="$(pwd)"
tmpdir="$(wvmktempdir)"
export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

bup init
cd "$tmpdir"

WVSTART "cat-file"
mkdir src
date > src/foo
WVPASS bup index src
WVPASS bup save -n src src
WVPASS bup cat-file "src/latest/$(pwd)/src/foo" > cat-foo
WVPASS diff -u src/foo cat-foo

WVSTART "cat-file --meta"
WVPASS bup meta --create --no-paths src/foo > src-foo.meta
WVPASS bup cat-file --meta "src/latest/$(pwd)/src/foo" > cat-foo.meta
WVPASS diff -u \
    <(bup meta -tvvf src-foo.meta | grep -vE '^atime: ') \
    <(bup meta -tvvf cat-foo.meta | grep -vE '^atime: ')

WVSTART "cat-file --bupm"
WVPASS bup cat-file --bupm "src/latest/$(pwd)/src/" > bup-cat-bupm
src_hash=$(bup ls -s "src/latest/$(pwd)" | cut -d' ' -f 1)
bupm_hash=$(git ls-tree "$src_hash" | grep -F .bupm | cut -d' ' -f 3)
bupm_hash=$(echo "$bupm_hash" | cut -d'	' -f 1)
git cat-file blob "$bupm_hash" > git-cat-bupm
WVPASS cmp -b git-cat-bupm bup-cat-bupm

rm -rf "$tmpdir"
