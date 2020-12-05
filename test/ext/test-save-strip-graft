#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?
. dev/lib.sh || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }
compare-trees() { "$top/dev/compare-trees" "$@"; }

WVPASS cd "$tmpdir"


WVSTART "save --strip"
WVPASS force-delete "$BUP_DIR" src restore
WVPASS bup init
WVPASS mkdir -p src/x/y/z
WVPASS bup random 8k > src/x/y/random-1
WVPASS bup random 8k > src/x/y/z/random-2
WVPASS bup index -u src
WVPASS bup save --strip -n foo src/x/y
WVPASS bup restore -C restore /foo/latest
WVPASS compare-trees src/x/y/ restore/latest/


WVSTART "save --strip-path (relative)"
WVPASS force-delete "$BUP_DIR" src restore
WVPASS bup init
WVPASS mkdir -p src/x/y/z
WVPASS bup random 8k > src/x/y/random-1
WVPASS bup random 8k > src/x/y/z/random-2
WVPASS bup index -u src
WVPASS bup save --strip-path src -n foo src/x
WVPASS bup restore -C restore /foo/latest
WVPASS compare-trees src/ restore/latest/


WVSTART "save --strip-path (absolute)"
WVPASS force-delete "$BUP_DIR" src restore
WVPASS bup init
WVPASS mkdir -p src/x/y/z
WVPASS bup random 8k > src/x/y/random-1
WVPASS bup random 8k > src/x/y/z/random-2
WVPASS bup index -u src
WVPASS bup save --strip-path "$tmpdir" -n foo src
WVPASS bup restore -C restore /foo/latest
WVPASS compare-trees src/ "restore/latest/src/"


WVSTART "save --strip-path (no match)"
if test $(WVPASS path-filesystems . | WVPASS sort -u | WVPASS wc -l) -ne 1
then
    # Skip the test because the attempt to restore parent dirs to the
    # current filesystem may fail -- i.e. running from
    # /foo/ext4/bar/btrfs will fail when bup tries to restore linux
    # attrs above btrfs to the restore tree *inside* btrfs.
    # FIXME: add WVSKIP
    echo "(running from tree with mixed filesystems; skipping test)" 1>&2
    exit 0
else
    WVPASS force-delete "$BUP_DIR" src restore
    WVPASS bup init
    WVPASS mkdir -p src/x/y/z
    WVPASS bup random 8k > src/x/y/random-1
    WVPASS bup random 8k > src/x/y/z/random-2
    WVPASS bup index -u src
    WVPASS bup save --strip-path foo -n foo src/x
    WVPASS bup restore -C restore /foo/latest
    WVPASS compare-trees src/ "restore/latest/$tmpdir/src/"
fi


WVSTART "save --graft (empty graft points disallowed)"
WVPASS force-delete "$BUP_DIR" src restore
WVPASS bup init
WVPASS mkdir src
WVFAIL bup save --graft =/grafted -n graft-point-absolute src 2>&1 \
    | WVPASS grep 'error: a graft point cannot be empty'
WVFAIL bup save --graft $top/$tmp= -n graft-point-absolute src 2>&1 \
    | WVPASS grep 'error: a graft point cannot be empty'


WVSTART "save --graft /x/y=/a/b (relative paths)"
WVPASS force-delete "$BUP_DIR" src restore
WVPASS bup init
WVPASS mkdir -p src/x/y/z
WVPASS bup random 8k > src/x/y/random-1
WVPASS bup random 8k > src/x/y/z/random-2
WVPASS bup index -u src
WVPASS bup save --graft src=x -n foo src
WVPASS bup restore -C restore /foo/latest
WVPASS compare-trees src/ "restore/latest/$tmpdir/x/"


WVSTART "save --graft /x/y=/a/b (matching structure)"
WVPASS force-delete "$BUP_DIR" src restore
WVPASS bup init
WVPASS mkdir -p src/x/y/z
WVPASS bup random 8k > src/x/y/random-1
WVPASS bup random 8k > src/x/y/z/random-2
WVPASS bup index -u src
WVPASS bup save -v --graft "$tmpdir/src/x/y=$tmpdir/src/a/b" -n foo src/x/y
WVPASS bup restore -C restore /foo/latest
WVPASS compare-trees src/x/y/ "restore/latest/$tmpdir/src/a/b/"


WVSTART "save --graft /x/y=/a (shorter target)"
WVPASS force-delete "$BUP_DIR" src restore
WVPASS bup init
WVPASS mkdir -p src/x/y/z
WVPASS bup random 8k > src/x/y/random-1
WVPASS bup random 8k > src/x/y/z/random-2
WVPASS bup index -u src
WVPASS bup save -v --graft "$tmpdir/src/x/y=/a" -n foo src/x/y
WVPASS bup restore -C restore /foo/latest
WVPASS compare-trees src/x/y/ "restore/latest/a/"


WVSTART "save --graft /x=/a/b (longer target)"
WVPASS force-delete "$BUP_DIR" src restore
WVPASS bup init
WVPASS mkdir -p src/x/y/z
WVPASS bup random 8k > src/x/y/random-1
WVPASS bup random 8k > src/x/y/z/random-2
WVPASS bup index -u src
WVPASS bup save -v --graft "$tmpdir/src=$tmpdir/src/a/b/c" -n foo src
WVPASS bup restore -C restore /foo/latest
WVPASS compare-trees src/ "restore/latest/$tmpdir/src/a/b/c/"


WVSTART "save --graft /x=/ (root target)"
WVPASS force-delete "$BUP_DIR" src restore
WVPASS bup init
WVPASS mkdir -p src/x/y/z
WVPASS bup random 8k > src/x/y/random-1
WVPASS bup random 8k > src/x/y/z/random-2
WVPASS bup index -u src
WVPASS bup save -v --graft "$tmpdir/src/x=/" -n foo src/x
WVPASS bup restore -C restore /foo/latest
WVPASS compare-trees src/x/ "restore/latest/"


#WVSTART "save --graft /=/x/ (root source)"
# FIXME: Not tested for now -- will require cleverness, or caution as root.


WVSTART "save collision"
WVPASS force-delete "$BUP_DIR" src restore
WVPASS bup init
WVPASS mkdir -p src/x/1 src/y/1
WVPASS bup index -u src
WVFAIL bup save --strip -n foo src/x src/y 2> tmp-err.log
WVPASS grep -F "error: ignoring duplicate path 1 in /" tmp-err.log


WVPASS rm -rf "$tmpdir"
