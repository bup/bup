#!/usr/bin/env bash
. wvtest.sh
. wvtest-bup.sh
. t/lib.sh

set -o pipefail

top="$(WVPASS /bin/pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?
export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS cd "$tmpdir"

WVSTART "init"

WVPASS bup init

WVSTART "index"
D=bupdata.tmp
WVPASS force-delete $D
WVPASS mkdir $D
WVFAIL bup index --exclude-from $D/cannot-exist $D
WVPASSEQ "$(bup index --check -p)" ""
WVPASSEQ "$(bup index --check -p $D)" ""
WVFAIL [ -e $D.fake ]
WVFAIL bup index --check -u $D.fake
WVPASS bup index --check -u $D
WVPASSEQ "$(bup index --check -p $D)" "$D/"
WVPASS touch $D/a
WVPASS bup random 128k >$D/b
WVPASS mkdir $D/d $D/d/e
WVPASS bup random 512 >$D/f
WVPASS ln -s non-existent-file $D/g
WVPASSEQ "$(bup index -s $D/)" "A $D/"
WVPASSEQ "$(bup index -s $D/b)" ""
WVPASSEQ "$(bup index --check -us $D/b)" "A $D/b"
WVPASSEQ "$(bup index --check -us $D/b $D/d)" \
"A $D/d/e/
A $D/d/
A $D/b"
WVPASS touch $D/d/z
WVPASS bup tick
WVPASSEQ "$(bup index --check -usx $D)" \
"A $D/g
A $D/f
A $D/d/z
A $D/d/e/
A $D/d/
A $D/b
A $D/a
A $D/"
WVPASSEQ "$(bup index --check -us $D/a $D/b --fake-valid)" \
"  $D/b
  $D/a"
WVPASSEQ "$(bup index --check -us $D/a)" "  $D/a"  # stays unmodified
WVPASSEQ "$(bup index --check -us $D/d --fake-valid)" \
"  $D/d/z
  $D/d/e/
  $D/d/"
WVPASS touch $D/d/z
WVPASS bup index -u $D/d/z  # becomes modified
WVPASSEQ "$(bup index -s $D/a $D $D/b)" \
"A $D/g
A $D/f
M $D/d/z
  $D/d/e/
M $D/d/
  $D/b
  $D/a
A $D/"

WVPASS bup index -u $D/d/e $D/a --fake-invalid
WVPASSEQ "$(cd $D && bup index -m .)" \
"./g
./f
./d/z
./d/e/
./d/
./a
./"
WVPASSEQ "$(cd $D && bup index -m)" \
"g
f
d/z
d/e/
d/
a
./"
WVPASSEQ "$(cd $D && bup index -s .)" "$(cd $D && bup index -s .)"

WVFAIL bup save -t $D/doesnt-exist-filename

WVPASS mv "$BUP_DIR/bupindex" "$BUP_DIR/bi.old"
WVFAIL bup save -t $D/d/e/fifotest
WVPASS mkfifo $D/d/e/fifotest
WVPASS bup index -u $D/d/e/fifotest
WVPASS bup save -t $D/d/e/fifotest
WVPASS bup save -t $D/d/e
WVPASS rm -f $D/d/e/fifotest
WVPASS bup index -u $D/d/e
WVFAIL bup save -t $D/d/e/fifotest
WVPASS mv "$BUP_DIR/bi.old" "$BUP_DIR/bupindex"

WVPASS bup index -u $D/d/e
WVPASS bup save -t $D/d/e
WVPASSEQ "$(cd $D && bup index -m)" \
"g
f
d/z
d/
a
./"
WVPASS bup save -t $D/d
WVPASS bup index --fake-invalid $D/d/z
WVPASS bup save -t $D/d/z
WVPASS bup save -t $D/d/z  # test regenerating trees when no files are changed
WVPASS bup save -t $D/d
WVPASSEQ "$(cd $D && bup index -m)" \
"g
f
a
./"
WVPASS bup save -r ":$BUP_DIR" -n r-test $D
WVFAIL bup save -r ":$BUP_DIR/fake/path" -n r-test $D
WVFAIL bup save -r ":$BUP_DIR" -n r-test $D/fake/path

WVSTART "split"
WVPASS echo a >a.tmp
WVPASS echo b >b.tmp
WVPASS bup split -b a.tmp >taga.tmp
WVPASS bup split -b b.tmp >tagb.tmp
WVPASS cat a.tmp b.tmp | WVPASS bup split -b >tagab.tmp
WVPASSEQ $(cat taga.tmp | wc -l) 1
WVPASSEQ $(cat tagb.tmp | wc -l) 1
WVPASSEQ $(cat tagab.tmp | wc -l) 1
WVPASSEQ $(cat tag[ab].tmp | wc -l) 2
WVPASSEQ "$(bup split -b a.tmp b.tmp)" "$(cat tagab.tmp)"
WVPASSEQ "$(bup split -b --keep-boundaries a.tmp b.tmp)" "$(cat tag[ab].tmp)"
WVPASSEQ "$(cat tag[ab].tmp | bup split -b --keep-boundaries --git-ids)" \
         "$(cat tag[ab].tmp)"
WVPASSEQ "$(cat tag[ab].tmp | bup split -b --git-ids)" \
         "$(cat tagab.tmp)"
WVPASS bup split --bench -b <"$top/t/testfile1" >tags1.tmp
WVPASS bup split -vvvv -b "$top/t/testfile2" >tags2.tmp
WVPASS echo -n "" | bup split -n split_empty_string.tmp
WVPASS bup margin
WVPASS bup midx -f
WVPASS bup midx --check -a
WVPASS bup midx -o "$BUP_DIR/objects/pack/test1.midx" \
	"$BUP_DIR"/objects/pack/*.idx
WVPASS bup midx --check -a
WVPASS bup midx -o "$BUP_DIR"/objects/pack/test1.midx \
	"$BUP_DIR"/objects/pack/*.idx \
	"$BUP_DIR"/objects/pack/*.idx
WVPASS bup midx --check -a
all=$(echo "$BUP_DIR"/objects/pack/*.idx "$BUP_DIR"/objects/pack/*.midx)
WVPASS bup midx -o "$BUP_DIR"/objects/pack/zzz.midx $all
WVPASS bup tick
WVPASS bup midx -o "$BUP_DIR"/objects/pack/yyy.midx $all
WVPASS bup midx -a
WVPASSEQ "$(echo "$BUP_DIR"/objects/pack/*.midx)" \
	""$BUP_DIR"/objects/pack/yyy.midx"
WVPASS bup margin
WVPASS bup split -t "$top/t/testfile2" >tags2t.tmp
WVPASS bup split -t "$top/t/testfile2" --fanout 3 >tags2tf.tmp
WVPASS bup split -r "$BUP_DIR" -c "$top/t/testfile2" >tags2c.tmp
WVPASS bup split -r ":$BUP_DIR" -c "$top/t/testfile2" >tags2c.tmp
WVPASS ls -lR \
    | WVPASS bup split -r ":$BUP_DIR" -c --fanout 3 --max-pack-objects 3 -n lslr \
    || exit $?
WVPASS bup ls
WVFAIL bup ls /does-not-exist
WVPASS bup ls /lslr
WVPASS bup ls /lslr/latest
WVPASS bup ls /lslr/latest/
#WVPASS bup ls /lslr/1971-01-01   # all dates always exist
WVFAIL diff -u tags1.tmp tags2.tmp

# fanout must be different from non-fanout
WVFAIL diff tags2t.tmp tags2tf.tmp
WVPASS wc -c "$top/t/testfile1" "$top/t/testfile2"
WVPASS wc -l tags1.tmp tags2.tmp

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

WVSTART "join"
WVPASS bup join $(cat tags1.tmp) >out1.tmp
WVPASS bup join <tags2.tmp >out2.tmp
WVPASS bup join <tags2t.tmp -o out2t.tmp
WVPASS bup join -r "$BUP_DIR" <tags2c.tmp >out2c.tmp
WVPASS bup join -r ":$BUP_DIR" <tags2c.tmp >out2c.tmp
WVPASS diff -u "$top/t/testfile1" out1.tmp
WVPASS diff -u "$top/t/testfile2" out2.tmp
WVPASS diff -u "$top/t/testfile2" out2t.tmp
WVPASS diff -u "$top/t/testfile2" out2c.tmp
WVPASSEQ "$(bup join split_empty_string.tmp)" ""

WVSTART "save/git-fsck"
(
    WVPASS cd "$BUP_DIR"
    #git repack -Ad
    #git prune
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
rm -f split_empty_string.tmp
WVPASS bup restore split_empty_string.tmp/latest/split_empty_string.tmp
WVPASSEQ "$(cat split_empty_string.tmp)" ""

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
    real_pwd="$(WVPASS realpath .)" || exit $?
    real_tmp="$(WVPASS realpath /tmp/.)" || exit $?
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
