#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS bup init
WVPASS cd "$tmpdir"

WVSTART "cat-file"
WVPASS mkdir src
WVPASS date > src/foo
WVPASS bup index src
WVPASS bup save -n src src
WVPASS bup cat-file "src/latest/$(pwd)/src/foo" > cat-foo
WVPASS diff -u src/foo cat-foo

WVSTART "cat-file --meta"
WVPASS bup meta --create --no-paths src/foo > src-foo.meta
WVPASS bup cat-file --meta "src/latest/$(pwd)/src/foo" > cat-foo.meta

WVPASS bup meta -tvvf src-foo.meta | WVPASS grep -vE '^atime: ' > src-foo.list
WVPASS bup meta -tvvf cat-foo.meta | WVPASS grep -vE '^atime: ' > cat-foo.list
WVPASS diff -u src-foo.list cat-foo.list

WVSTART "cat-file --bupm"
WVPASS bup cat-file --bupm "src/latest/$(pwd)/src/" > bup-cat-bupm
src_hash=$(WVPASS bup ls -s "src/latest/$(pwd)" | cut -d' ' -f 1) || exit $?
bupm_hash=$(WVPASS git ls-tree "$src_hash" | grep -F .bupm | cut -d' ' -f 3) \
    || exit $?
bupm_hash=$(WVPASS echo "$bupm_hash" | cut -d'	' -f 1) || exit $?
WVPASS "$top/dev/git-cat-tree" "$bupm_hash" > git-cat-bupm
if ! cmp git-cat-bupm bup-cat-bupm; then
    cmp -l git-cat-bupm bup-cat-bupm
    diff -uN <(bup meta -tvvf git-cat-bupm) <(bup meta -tvvf bup-cat-bupm)
    WVPASS cmp git-cat-bupm bup-cat-bupm
fi

WVPASS rm -rf "$tmpdir"
