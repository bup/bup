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


WVSTART "index excludes bupdir"
WVPASS force-delete src "$BUP_DIR"
WVPASS bup init
WVPASS mkdir src
WVPASS touch src/a
WVPASS bup random 128k >src/b
WVPASS mkdir src/d src/d/e
WVPASS bup random 512 >src/f
WVPASS bup index -ux src
WVPASS bup save -n exclude-bupdir src
WVPASSEQ "$(bup ls -AF "exclude-bupdir/latest/$tmpdir/src/")" "a
b
d/
f"


WVSTART "index --exclude"
WVPASS force-delete src "$BUP_DIR"
WVPASS bup init
WVPASS mkdir src
WVPASS touch src/a
WVPASS bup random 128k >src/b
WVPASS mkdir src/d src/d/e
WVPASS bup random 512 >src/f
WVPASS bup random 512 >src/j
WVPASS bup index -ux --exclude src/d --exclude src/j src
WVPASS bup save -n exclude src
WVPASSEQ "$(bup ls "exclude/latest/$tmpdir/src/")" "a
b
f"
WVPASS mkdir src/g src/h
WVPASS bup index -ux --exclude src/d --exclude $tmpdir/src/g --exclude src/h \
    --exclude "$tmpdir/src/j" src
WVPASS bup save -n exclude src
WVPASSEQ "$(bup ls "exclude/latest/$tmpdir/src/")" "a
b
f"


WVSTART "index --exclude-from"
WVPASS force-delete src "$BUP_DIR"
WVPASS bup init
WVPASS mkdir src
WVPASS echo "src/d
 $tmpdir/src/g
src/h
src/i" > exclude-list
WVPASS touch src/a
WVPASS bup random 128k >src/b
WVPASS mkdir src/d src/d/e
WVPASS bup random 512 >src/f
WVPASS mkdir src/g src/h
WVPASS bup random 128k > src/i
WVPASS bup index -ux --exclude-from exclude-list src
WVPASS bup save -n exclude-from src
WVPASSEQ "$(bup ls "exclude-from/latest/$tmpdir/src/")" "a
b
f"
WVPASS rm exclude-list


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
# exclude-rx-file includes blank lines to check that we ignore them.
WVPASS echo "^$(pwd)/src/sub1/

" > exclude-rx-file
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


# bup restore --exclude-rx-from ...
# =================================

WVSTART "restore --exclude-rx-from"
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
WVPASS echo "^/sub1/" > exclude-rx-file
WVPASS bup restore -C buprestore.tmp \
    --exclude-rx-from exclude-rx-file /bupdir/latest/
actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
WVPASSEQ "$actual" ".
./a
./b
./sub2
./sub2/b"

WVPASS rm -rf "$tmpdir"
