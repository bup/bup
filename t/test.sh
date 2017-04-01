#!/usr/bin/env bash
. wvtest.sh
. wvtest-bup.sh
. t/lib.sh

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?
export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS cd "$tmpdir"

WVSTART "init"

WVPASS bup init

D=bupdata.tmp
WVPASS force-delete $D
WVPASS mkdir $D
WVPASS touch $D/a
WVPASS bup random 128k >$D/b
WVPASS mkdir $D/d $D/d/e
WVPASS bup random 512 >$D/f
WVPASS touch $D/d/z
WVPASS touch $D/d/z
WVPASS bup index $D
WVPASS bup save -t $D

WVSTART "bloom"
WVPASS bup bloom -c $(ls -1 "$BUP_DIR"/objects/pack/*.idx|head -n1)
WVPASS rm "$BUP_DIR"/objects/pack/bup.bloom
WVPASS bup bloom -k 4
WVPASS bup bloom -c $(ls -1 "$BUP_DIR"/objects/pack/*.idx|head -n1)
WVPASS bup bloom -d "$BUP_DIR"/objects/pack --ruin --force
WVFAIL bup bloom -c $(ls -1 "$BUP_DIR"/objects/pack/*.idx|head -n1)
WVPASS bup bloom --force -k 5
WVPASS bup bloom -c $(ls -1 "$BUP_DIR"/objects/pack/*.idx|head -n1)

WVSTART "memtest"
WVPASS bup memtest -c1 -n100
WVPASS bup memtest -c1 -n100 --existing

WVSTART "save/git-fsck"
(
    WVPASS cd "$BUP_DIR"
    #git repack -Ad
    #git prune
    WVPASS bup random 4k | WVPASS bup split -b
    (WVPASS cd "$top/t/sampledata" && WVPASS bup save -vvn master /) || exit $?
    result="$(git fsck --full --strict 2>&1)" || exit $?
    n=$(echo "$result" |
        WVFAIL egrep -v 'dangling (commit|tree|blob)' |
        WVPASS tee -a /dev/stderr |
        WVPASS wc -l) || exit $?
    WVPASS [ "$n" -eq 0 ]
) || exit $?

WVSTART "restore"
WVPASS force-delete buprestore.tmp
WVFAIL bup restore boink
WVPASS touch "$tmpdir/$D/$D"
WVPASS bup index -u "$tmpdir/$D"
WVPASS bup save -n master /
WVPASS bup restore -C buprestore.tmp "/master/latest/$tmpdir/$D"
WVPASSEQ "$(ls buprestore.tmp)" "bupdata.tmp"
WVPASS force-delete buprestore.tmp
WVPASS bup restore -C buprestore.tmp "/master/latest/$tmpdir/$D/"
WVPASS touch $D/non-existent-file buprestore.tmp/non-existent-file # else diff fails
WVPASS diff -ur $D/ buprestore.tmp/
WVPASS force-delete buprestore.tmp
WVPASS echo -n "" | WVPASS bup split -n split_empty_string.tmp
WVPASS bup restore -C buprestore.tmp split_empty_string.tmp/latest/
WVPASSEQ "$(cat buprestore.tmp/data)" ""

(
    tmp=testrestore.tmp
    WVPASS force-delete $tmp
    WVPASS mkdir $tmp
    export BUP_DIR="$(pwd)/$tmp/bup"
    WVPASS WVPASS bup init
    WVPASS mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save --strip -n foo $tmp/src

    WVSTART "restore /foo/latest"
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS "$top/t/compare-trees" $tmp/src/ $tmp/restore/latest/

    WVSTART "restore /foo/latest/"
    WVPASS force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/
    for x in $tmp/src/*; do
        WVPASS "$top/t/compare-trees" $x/ $tmp/restore/$(basename $x);
    done

    WVSTART "restore /foo/latest/."
    WVPASS force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/.
    WVPASS "$top/t/compare-trees" $tmp/src/ $tmp/restore/

    WVSTART "restore /foo/latest/x"
    WVPASS force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/x
    WVPASS "$top/t/compare-trees" $tmp/src/x/ $tmp/restore/x/

    WVSTART "restore /foo/latest/x/"
    WVPASS force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/x/
    for x in $tmp/src/x/*; do
        WVPASS "$top/t/compare-trees" $x/ $tmp/restore/$(basename $x);
    done

    WVSTART "restore /foo/latest/x/."
    WVPASS force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/x/.
    WVPASS "$top/t/compare-trees" $tmp/src/x/ $tmp/restore/
) || exit $?


WVSTART "ftp"
WVPASS bup ftp "cat /master/latest/$tmpdir/$D/b" >$D/b.new
WVPASS bup ftp "cat /master/latest/$tmpdir/$D/f" >$D/f.new
WVPASS bup ftp "cat /master/latest/$tmpdir/$D/f"{,} >$D/f2.new
WVPASS bup ftp "cat /master/latest/$tmpdir/$D/a" >$D/a.new
WVPASSEQ "$(sha1sum <$D/b)" "$(sha1sum <$D/b.new)"
WVPASSEQ "$(sha1sum <$D/f)" "$(sha1sum <$D/f.new)"
WVPASSEQ "$(cat $D/f.new{,} | sha1sum)" "$(sha1sum <$D/f2.new)"
WVPASSEQ "$(sha1sum <$D/a)" "$(sha1sum <$D/a.new)"

WVSTART "tag"
WVFAIL bup tag -d v0.n 2>/dev/null
WVFAIL bup tag v0.n non-existant 2>/dev/null
WVPASSEQ "$(bup tag)" ""
WVPASS bup tag v0.1 master
WVPASSEQ "$(bup tag)" "v0.1"
WVFAIL bup tag v0.1 master
WVPASS bup tag -f v0.1 master
WVPASS bup tag -d v0.1
WVPASS bup tag -f -d v0.1
WVFAIL bup tag -d v0.1


WVSTART "save (no index)"
(
    tmp=save-no-index.tmp
    WVPASS force-delete $tmp
    WVPASS mkdir $tmp
    export BUP_DIR="$(WVPASS pwd)/$tmp/bup" || exit $?
    WVPASS bup init
    WVFAIL bup save -n nothing /
    WVPASS rm -r "$tmp"
) || exit $?

WVSTART "indexfile"
D=indexfile.tmp
INDEXFILE=tmpindexfile.tmp
WVPASS rm -f $INDEXFILE
WVPASS force-delete $D
WVPASS mkdir $D
export BUP_DIR="$D/.bup"
WVPASS bup init
WVPASS touch $D/a
WVPASS touch $D/b
WVPASS mkdir $D/c
WVPASS bup index -ux $D
WVPASS bup save --strip -n bupdir $D
WVPASSEQ "$(bup ls -F bupdir/latest/)" "a
b
c/"
WVPASS bup index -f $INDEXFILE --exclude=$D/c -ux $D
WVPASS bup save --strip -n indexfile -f $INDEXFILE $D
WVPASSEQ "$(bup ls indexfile/latest/)" "a
b"


WVSTART "import-rsnapshot"
D=rsnapshot.tmp
export BUP_DIR="$tmpdir/$D/.bup"
WVPASS force-delete $D
WVPASS mkdir $D
WVPASS bup init
WVPASS mkdir -p $D/hourly.0/buptest/a
WVPASS touch $D/hourly.0/buptest/a/b
WVPASS mkdir -p $D/hourly.0/buptest/c/d
WVPASS touch $D/hourly.0/buptest/c/d/e
WVPASS true
WVPASS bup import-rsnapshot $D/
WVPASSEQ "$(bup ls -F buptest/latest/)" "a/
c/"


WVSTART "save disjoint top-level directories"
(
    # Resolve any symlinks involving the top top-level dirs.
    real_pwd="$(WVPASS resolve-parent .)" || exit $?
    real_tmp="$(WVPASS resolve-parent /tmp/.)" || exit $?
    pwd_top="$(echo $real_pwd | WVPASS awk -F "/" '{print $2}')" || exit $?
    tmp_top="$(echo $real_tmp | WVPASS awk -F "/" '{print $2}')" || exit $?

    if [ "$pwd_top" = "$tmp_top" ]; then
        echo "(running from within /$tmp_top; skipping test)" 1>&2
        exit 0
    fi
    D=bupdata.tmp
    WVPASS force-delete $D
    WVPASS mkdir -p $D/x
    WVPASS date > $D/x/1
    tmpdir2="$(WVPASS mktemp -d $real_tmp/bup-test-XXXXXXX)" || exit $?
    cleanup() { WVPASS rm -r "$tmpdir2"; }
    WVPASS trap cleanup EXIT
    WVPASS date > "$tmpdir2/2"

    export BUP_DIR="$tmpdir/bup"
    WVPASS test -d "$BUP_DIR" && WVPASS rm -r "$BUP_DIR"

    WVPASS bup init
    WVPASS bup index -vu $(pwd)/$D/x "$tmpdir2"
    WVPASS bup save -t -n src $(pwd)/$D/x "$tmpdir2"

    # For now, assume that "ls -a" and "sort" use the same order.
    actual="$(WVPASS bup ls -AF src/latest)" || exit $?
    expected="$(echo -e "$pwd_top/\n$tmp_top/" | WVPASS sort)" || exit $?
    WVPASSEQ "$actual" "$expected"
) || exit $?

WVPASS rm -rf "$tmpdir"
