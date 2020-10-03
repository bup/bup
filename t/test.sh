#!/usr/bin/env bash
. wvtest.sh
. wvtest-bup.sh
. t/lib.sh

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?
export BUP_DIR="$tmpdir/bup"
export LANGUAGE=en

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


WVSTART features
expect_py_ver=$(LC_CTYPE=C "$top/config/bin/python" \
                        -c 'import platform; print(platform.python_version())') \
    || exit $?
actual_py_ver=$(bup features | grep Python: | sed -Ee 's/ +Python: //') || exit $?
WVPASSEQ "$expect_py_ver" "$actual_py_ver"

WVPASS rm -rf "$tmpdir"
