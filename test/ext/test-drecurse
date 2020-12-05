#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?
. dev/lib.sh || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS cd "$tmpdir"

# These tests aren't comprehensive, but test-save-restore-excludes.sh
# exercises some of the same code more thoroughly via index, and
# --xdev is handled in test-xdev.sh.

WVSTART "drecurse"
WVPASS bup init
WVPASS mkdir src src/a src/b
WVPASS touch src/a/1 src/a/2 src/b/1 src/b/2 src/c
(cd src && WVPASS ln -s a a-link)
WVPASSEQ "$(bup drecurse src)" "src/c
src/b/2
src/b/1
src/b/
src/a/2
src/a/1
src/a/
src/a-link
src/"

WVSTART "drecurse --exclude (file)"
WVPASSEQ "$(bup drecurse --exclude src/b/2 src)" "src/c
src/b/1
src/b/
src/a/2
src/a/1
src/a/
src/a-link
src/"

WVSTART "drecurse --exclude (dir)"
WVPASSEQ "$(bup drecurse --exclude src/b/ src)" "src/c
src/a/2
src/a/1
src/a/
src/a-link
src/"

WVSTART "drecurse --exclude (symlink)"
WVPASSEQ "$(bup drecurse --exclude src/a-link src)" "src/c
src/b/2
src/b/1
src/b/
src/a/2
src/a/1
src/a/
src/"

WVSTART "drecurse --exclude (absolute path)"
WVPASSEQ "$(bup drecurse --exclude src/b/2 "$(pwd)/src")" "$(pwd)/src/c
$(pwd)/src/b/1
$(pwd)/src/b/
$(pwd)/src/a/2
$(pwd)/src/a/1
$(pwd)/src/a/
$(pwd)/src/a-link
$(pwd)/src/"

WVSTART "drecurse --exclude-from"
WVPASS echo "src/b" > exclude-list
WVPASSEQ "$(bup drecurse --exclude-from exclude-list src)" "src/c
src/a/2
src/a/1
src/a/
src/a-link
src/"

WVSTART "drecurse --exclude-rx (trivial)"
WVPASSEQ "$(bup drecurse --exclude-rx '^src/b' src)" "src/c
src/a/2
src/a/1
src/a/
src/a-link
src/"

WVSTART "drecurse --exclude-rx (trivial - absolute path)"
WVPASSEQ "$(bup drecurse --exclude-rx "^$(pwd)/src/b" "$(pwd)/src")" \
"$(pwd)/src/c
$(pwd)/src/a/2
$(pwd)/src/a/1
$(pwd)/src/a/
$(pwd)/src/a-link
$(pwd)/src/"

WVPASS rm -rf "$tmpdir"
