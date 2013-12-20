#!/usr/bin/env bash
. ./wvtest-bup.sh

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS bup init
WVPASS cd "$tmpdir"


# bup index --exclude-rx ...
# ==========================

WVSTART "index --exclude-rx '^/foo' (root anchor)"
WVPASS rm -rf src "$BUP_DIR" buprestore.tmp
WVPASS bup init
WVPASS mkdir src
WVPASS touch src/a
WVPASS touch src/b
WVPASS mkdir src/sub1
WVPASS mkdir src/sub2
WVPASS touch src/sub1/a
WVPASS touch src/sub2/b
WVPASS bup index -u src --exclude-rx "^$(pwd)/src/sub1/"
WVPASS bup save --strip -n bupdir src
WVPASS bup restore -C buprestore.tmp /bupdir/latest/
actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
WVPASSEQ "$actual" ".
./a
./b
./sub2
./sub2/b"

WVSTART "index --exclude-rx '/foo$' (non-dir, tail anchor)"
WVPASS rm -rf src "$BUP_DIR" buprestore.tmp
WVPASS bup init
WVPASS mkdir src
WVPASS touch src/a
WVPASS touch src/b
WVPASS touch src/foo
WVPASS mkdir src/sub
WVPASS mkdir src/sub/foo
WVPASS touch src/sub/foo/a
WVPASS bup index -u src --exclude-rx '/foo$'
WVPASS bup save --strip -n bupdir src
WVPASS bup restore -C buprestore.tmp /bupdir/latest/
actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
WVPASSEQ "$actual" ".
./a
./b
./sub
./sub/foo
./sub/foo/a"

WVSTART "index --exclude-rx '/foo/$' (dir, tail anchor)"
WVPASS rm -rf src "$BUP_DIR" buprestore.tmp
WVPASS bup init
WVPASS mkdir src
WVPASS touch src/a
WVPASS touch src/b
WVPASS touch src/foo
WVPASS mkdir src/sub
WVPASS mkdir src/sub/foo
WVPASS touch src/sub/foo/a
WVPASS bup index -u src --exclude-rx '/foo/$'
WVPASS bup save --strip -n bupdir src
WVPASS bup restore -C buprestore.tmp /bupdir/latest/
actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
WVPASSEQ "$actual" ".
./a
./b
./foo
./sub"

WVSTART "index --exclude-rx '/foo/.' (dir content)"
WVPASS rm -rf src "$BUP_DIR" buprestore.tmp
WVPASS bup init
WVPASS mkdir src
WVPASS touch src/a
WVPASS touch src/b
WVPASS touch src/foo
WVPASS mkdir src/sub
WVPASS mkdir src/sub/foo
WVPASS touch src/sub/foo/a
WVPASS bup index -u src --exclude-rx '/foo/.'
WVPASS bup save --strip -n bupdir src
WVPASS bup restore -C buprestore.tmp /bupdir/latest/
actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
WVPASSEQ "$actual" ".
./a
./b
./foo
./sub
./sub/foo"


# bup index --exclude-rx-from ...
# ===============================
WVSTART "index --exclude-rx-from"
WVPASS rm -rf src "$BUP_DIR" buprestore.tmp
WVPASS bup init
WVPASS mkdir src
WVPASS touch src/a
WVPASS touch src/b
WVPASS mkdir src/sub1
WVPASS mkdir src/sub2
WVPASS touch src/sub1/a
WVPASS touch src/sub2/b
WVPASS echo "^$(pwd)/src/sub1/" > exclude-rx-file
WVPASS bup index -u src --exclude-rx-from exclude-rx-file
WVPASS bup save --strip -n bupdir src
WVPASS bup restore -C buprestore.tmp /bupdir/latest/
actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
WVPASSEQ "$actual" ".
./a
./b
./sub2
./sub2/b"


# bup restore --exclude-rx ...
# ============================

WVSTART "restore --exclude-rx '^/foo' (root anchor)"
WVPASS rm -rf src "$BUP_DIR" buprestore.tmp
WVPASS bup init
WVPASS mkdir src
WVPASS touch src/a
WVPASS touch src/b
WVPASS mkdir src/sub1
WVPASS mkdir src/sub2
WVPASS touch src/sub1/a
WVPASS touch src/sub2/b
WVPASS bup index -u src
WVPASS bup save --strip -n bupdir src
WVPASS bup restore -C buprestore.tmp --exclude-rx "^/sub1/" /bupdir/latest/
actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
WVPASSEQ "$actual" ".
./a
./b
./sub2
./sub2/b"

WVSTART "restore --exclude-rx '/foo$' (non-dir, tail anchor)"
WVPASS rm -rf src "$BUP_DIR" buprestore.tmp
WVPASS bup init
WVPASS mkdir src
WVPASS touch src/a
WVPASS touch src/b
WVPASS touch src/foo
WVPASS mkdir src/sub
WVPASS mkdir src/sub/foo
WVPASS touch src/sub/foo/a
WVPASS bup index -u src
WVPASS bup save --strip -n bupdir src
WVPASS bup restore -C buprestore.tmp --exclude-rx '/foo$' /bupdir/latest/
actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
WVPASSEQ "$actual" ".
./a
./b
./sub
./sub/foo
./sub/foo/a"

WVSTART "restore --exclude-rx '/foo/$' (dir, tail anchor)"
WVPASS rm -rf src "$BUP_DIR" buprestore.tmp
WVPASS bup init
WVPASS mkdir src
WVPASS touch src/a
WVPASS touch src/b
WVPASS touch src/foo
WVPASS mkdir src/sub
WVPASS mkdir src/sub/foo
WVPASS touch src/sub/foo/a
WVPASS bup index -u src
WVPASS bup save --strip -n bupdir src
WVPASS bup restore -C buprestore.tmp --exclude-rx '/foo/$' /bupdir/latest/
actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
WVPASSEQ "$actual" ".
./a
./b
./foo
./sub"

WVSTART "restore --exclude-rx '/foo/.' (dir content)"
WVPASS rm -rf src "$BUP_DIR" buprestore.tmp
WVPASS bup init
WVPASS mkdir src
WVPASS touch src/a
WVPASS touch src/b
WVPASS touch src/foo
WVPASS mkdir src/sub
WVPASS mkdir src/sub/foo
WVPASS touch src/sub/foo/a
WVPASS bup index -u src
WVPASS bup save --strip -n bupdir src
WVPASS bup restore -C buprestore.tmp --exclude-rx '/foo/.' /bupdir/latest/
actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
WVPASSEQ "$actual" ".
./a
./b
./foo
./sub
./sub/foo"


WVPASS rm -rf "$tmpdir"
