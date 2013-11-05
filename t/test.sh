#!/usr/bin/env bash
. wvtest.sh
. t/lib.sh

set -o pipefail

TOP="$(WVPASS /bin/pwd)" || exit $?
export BUP_DIR="$TOP/buptest.tmp"

bup()
{
    "$TOP/bup" "$@"
}

WVSTART "init"

WVPASS rm -rf "$BUP_DIR"
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

WVPASS mv $BUP_DIR/bupindex $BUP_DIR/bi.old
WVFAIL bup save -t $D/d/e/fifotest
WVPASS mkfifo $D/d/e/fifotest
WVPASS bup index -u $D/d/e/fifotest
WVPASS bup save -t $D/d/e/fifotest
WVPASS bup save -t $D/d/e
WVPASS rm -f $D/d/e/fifotest
WVPASS bup index -u $D/d/e
WVFAIL bup save -t $D/d/e/fifotest
WVPASS mv $BUP_DIR/bi.old $BUP_DIR/bupindex

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
WVPASS bup save -r :$BUP_DIR -n r-test $D
WVFAIL bup save -r :$BUP_DIR/fake/path -n r-test $D
WVFAIL bup save -r :$BUP_DIR -n r-test $D/fake/path

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
WVPASS bup split --bench -b <t/testfile1 >tags1.tmp
WVPASS bup split -vvvv -b t/testfile2 >tags2.tmp
WVPASS bup margin
WVPASS bup midx -f
WVPASS bup midx --check -a
WVPASS bup midx -o $BUP_DIR/objects/pack/test1.midx \
	$BUP_DIR/objects/pack/*.idx
WVPASS bup midx --check -a
WVPASS bup midx -o $BUP_DIR/objects/pack/test1.midx \
	$BUP_DIR/objects/pack/*.idx \
	$BUP_DIR/objects/pack/*.idx
WVPASS bup midx --check -a
all=$(echo $BUP_DIR/objects/pack/*.idx $BUP_DIR/objects/pack/*.midx)
WVPASS bup midx -o $BUP_DIR/objects/pack/zzz.midx $all
WVPASS bup tick
WVPASS bup midx -o $BUP_DIR/objects/pack/yyy.midx $all
WVPASS bup midx -a
WVPASSEQ "$(echo $BUP_DIR/objects/pack/*.midx)" \
	"$BUP_DIR/objects/pack/yyy.midx"
WVPASS bup margin
WVPASS bup split -t t/testfile2 >tags2t.tmp
WVPASS bup split -t t/testfile2 --fanout 3 >tags2tf.tmp
WVPASS bup split -r "$BUP_DIR" -c t/testfile2 >tags2c.tmp
WVPASS bup split -r :$BUP_DIR -c t/testfile2 >tags2c.tmp
WVPASS ls -lR \
    | WVPASS bup split -r :$BUP_DIR -c --fanout 3 --max-pack-objects 3 -n lslr \
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
WVPASS wc -c t/testfile1 t/testfile2
WVPASS wc -l tags1.tmp tags2.tmp

WVSTART "bloom"
WVPASS bup bloom -c $(ls -1 $BUP_DIR/objects/pack/*.idx|head -n1)
WVPASS rm $BUP_DIR/objects/pack/bup.bloom
WVPASS bup bloom -k 4
WVPASS bup bloom -c $(ls -1 $BUP_DIR/objects/pack/*.idx|head -n1)
WVPASS bup bloom -d buptest.tmp/objects/pack --ruin --force
WVFAIL bup bloom -c $(ls -1 $BUP_DIR/objects/pack/*.idx|head -n1)
WVPASS bup bloom --force -k 5
WVPASS bup bloom -c $(ls -1 $BUP_DIR/objects/pack/*.idx|head -n1)

WVSTART "memtest"
WVPASS bup memtest -c1 -n100
WVPASS bup memtest -c1 -n100 --existing

WVSTART "join"
WVPASS bup join $(cat tags1.tmp) >out1.tmp
WVPASS bup join <tags2.tmp >out2.tmp
WVPASS bup join <tags2t.tmp -o out2t.tmp
WVPASS bup join -r "$BUP_DIR" <tags2c.tmp >out2c.tmp
WVPASS bup join -r ":$BUP_DIR" <tags2c.tmp >out2c.tmp
WVPASS diff -u t/testfile1 out1.tmp
WVPASS diff -u t/testfile2 out2.tmp
WVPASS diff -u t/testfile2 out2t.tmp
WVPASS diff -u t/testfile2 out2c.tmp

WVSTART "save/git-fsck"
(
    WVPASS cd "$BUP_DIR"
    #git repack -Ad
    #git prune
    (WVPASS cd "$TOP/t/sampledata" && WVPASS bup save -vvn master /) || exit $?
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
WVPASS touch $TOP/$D/$D
WVPASS bup index -u $TOP/$D
WVPASS bup save -n master /
WVPASS bup restore -C buprestore.tmp "/master/latest/$TOP/$D"
WVPASSEQ "$(ls buprestore.tmp)" "bupdata.tmp"
WVPASS force-delete buprestore.tmp
WVPASS bup restore -C buprestore.tmp "/master/latest/$TOP/$D/"
WVPASS touch $D/non-existent-file buprestore.tmp/non-existent-file # else diff fails
WVPASS diff -ur $D/ buprestore.tmp/

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
    WVPASS t/compare-trees $tmp/src/ $tmp/restore/latest/

    WVSTART "restore /foo/latest/"
    WVPASS force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/
    for x in $tmp/src/*; do
        WVPASS t/compare-trees $x/ $tmp/restore/$(basename $x);
    done

    WVSTART "restore /foo/latest/."
    WVPASS force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/.
    WVPASS t/compare-trees $tmp/src/ $tmp/restore/

    WVSTART "restore /foo/latest/x"
    WVPASS force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/x
    WVPASS t/compare-trees $tmp/src/x/ $tmp/restore/x/

    WVSTART "restore /foo/latest/x/"
    WVPASS force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/x/
    for x in $tmp/src/x/*; do
        WVPASS t/compare-trees $x/ $tmp/restore/$(basename $x);
    done

    WVSTART "restore /foo/latest/x/."
    WVPASS force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/x/.
    WVPASS t/compare-trees $tmp/src/x/ $tmp/restore/
) || exit $?


WVSTART "ftp"
WVPASS bup ftp "cat /master/latest/$TOP/$D/b" >$D/b.new
WVPASS bup ftp "cat /master/latest/$TOP/$D/f" >$D/f.new
WVPASS bup ftp "cat /master/latest/$TOP/$D/f"{,} >$D/f2.new
WVPASS bup ftp "cat /master/latest/$TOP/$D/a" >$D/a.new
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
WVPASS bup tag -d v0.1

# This section destroys data in the bup repository, so it is done last.
WVSTART "fsck"
WVPASS bup fsck
WVPASS bup fsck --quick
if bup fsck --par2-ok; then
    WVSTART "fsck (par2)"
else
    WVSTART "fsck (PAR2 IS MISSING)"
fi
WVPASS bup fsck -g
WVPASS bup fsck -r
WVPASS bup damage $BUP_DIR/objects/pack/*.pack -n10 -s1 -S0
WVFAIL bup fsck --quick
WVFAIL bup fsck --quick --disable-par2
WVPASS chmod u+w $BUP_DIR/objects/pack/*.idx
WVPASS bup damage $BUP_DIR/objects/pack/*.idx -n10 -s1 -S0
WVFAIL bup fsck --quick -j4
WVPASS bup damage $BUP_DIR/objects/pack/*.pack -n10 -s1024 --percent 0.4 -S0
WVFAIL bup fsck --quick
WVFAIL bup fsck --quick -rvv -j99   # fails because repairs were needed
if bup fsck --par2-ok; then
    WVPASS bup fsck -r # ok because of repairs from last time
    WVPASS bup damage $BUP_DIR/objects/pack/*.pack -n202 -s1 --equal -S0
    WVFAIL bup fsck
    WVFAIL bup fsck -rvv   # too many errors to be repairable
    WVFAIL bup fsck -r   # too many errors to be repairable
else
    WVFAIL bup fsck --quick -r # still fails because par2 was missing
fi

WVSTART "exclude-bupdir"
D=exclude-bupdir.tmp
WVPASS force-delete $D
WVPASS mkdir $D
export BUP_DIR="$D/.bup"
WVPASS bup init
WVPASS touch $D/a
WVPASS bup random 128k >$D/b
WVPASS mkdir $D/d $D/d/e
WVPASS bup random 512 >$D/f
WVPASS bup index -ux $D
WVPASS bup save -n exclude-bupdir $D
WVPASSEQ "$(bup ls -a exclude-bupdir/latest/$TOP/$D/)" "a
b
d/
f"

WVSTART "exclude"
(
    D=exclude.tmp
    WVPASS force-delete $D
    WVPASS mkdir $D
    export BUP_DIR="$D/.bup"
    WVPASS bup init
    WVPASS touch $D/a
    WVPASS bup random 128k >$D/b
    WVPASS mkdir $D/d $D/d/e
    WVPASS bup random 512 >$D/f
    WVPASS bup random 512 >$D/j
    WVPASS bup index -ux --exclude $D/d --exclude $D/j $D
    WVPASS bup save -n exclude $D
    WVPASSEQ "$(bup ls exclude/latest/$TOP/$D/)" "a
b
f"
    WVPASS mkdir $D/g $D/h
    WVPASS bup index -ux --exclude $D/d --exclude $TOP/$D/g --exclude $D/h \
        --exclude $TOP/$D/j $D
    WVPASS bup save -n exclude $D
    WVPASSEQ "$(bup ls exclude/latest/$TOP/$D/)" "a
b
f"
) || exit $?

WVSTART "exclude-from"
(
    D=exclude-fromdir.tmp
    EXCLUDE_FILE=exclude-from.tmp
    WVPASS echo "$D/d 
 $TOP/$D/g
$D/h
$D/i" > $EXCLUDE_FILE
    WVPASS force-delete $D
    WVPASS mkdir $D
    export BUP_DIR="$D/.bup"
    WVPASS bup init
    WVPASS touch $D/a
    WVPASS bup random 128k >$D/b
    WVPASS mkdir $D/d $D/d/e
    WVPASS bup random 512 >$D/f
    WVPASS mkdir $D/g $D/h
    WVPASS bup random 128k > $D/i
    WVPASS bup index -ux --exclude-from $EXCLUDE_FILE $D
    WVPASS bup save -n exclude-from $D
    WVPASSEQ "$(bup ls exclude-from/latest/$TOP/$D/)" "a
b
f"
    WVPASS rm $EXCLUDE_FILE
) || exit $?

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

WVSTART "save --strip"
(
    tmp=graft-points.tmp
    WVPASS force-delete $tmp
    WVPASS mkdir $tmp
    export BUP_DIR="$(WVPASS pwd)/$tmp/bup" || exit $?
    WVPASS bup init
    WVPASS mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save --strip -n foo $tmp/src/x/y
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/x/y/ "$tmp/restore/latest/"
) || exit $?

WVSTART "save --strip-path (relative)"
(
    tmp=graft-points.tmp
    WVPASS force-delete $tmp
    WVPASS mkdir $tmp
    export BUP_DIR="$(WVPASS pwd)/$tmp/bup" || exit $?
    WVPASS bup init
    WVPASS mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save --strip-path $tmp/src -n foo $tmp/src/x
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/ "$tmp/restore/latest/"
) || exit $?

WVSTART "save --strip-path (absolute)"
(
    tmp=graft-points.tmp
    WVPASS force-delete $tmp
    WVPASS mkdir $tmp
    export BUP_DIR="$(WVPASS pwd)/$tmp/bup" || exit $?
    WVPASS bup init
    WVPASS mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save --strip-path "$TOP" -n foo $tmp/src
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/ "$tmp/restore/latest/$tmp/src/"
) || exit $?

WVSTART "save --strip-path (no match)"
(
    if test $(WVPASS path-filesystems . | WVPASS sort -u | WVPASS wc -l) -ne 1
    then
        # Skip the test because the attempt to restore parent dirs to
        # the current filesystem may fail -- i.e. running from
        # /foo/ext4/bar/btrfs will fail when bup tries to restore
        # linux attrs above btrfs to the restore tree *inside* btrfs.
        echo "(running from tree with mixed filesystems; skipping test)" 1>&2
        exit 0
    fi

    tmp=graft-points.tmp
    WVPASS force-delete $tmp
    WVPASS mkdir $tmp
    export BUP_DIR="$(WVPASS pwd)/$tmp/bup" || exit $?
    WVPASS bup init
    WVPASS mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save --strip-path $tmp/foo -n foo $tmp/src/x
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/ "$tmp/restore/latest/$TOP/$tmp/src/"
) || exit $?

WVSTART "save --graft (empty graft points disallowed)"
(
    tmp=graft-points.tmp
    WVPASS force-delete $tmp
    WVPASS mkdir $tmp
    export BUP_DIR="$(WVPASS pwd)/$tmp/bup" || exit $?
    WVPASS bup init
    WVFAIL bup save --graft =/grafted -n graft-point-absolute $tmp
    WVFAIL bup save --graft $TOP/$tmp= -n graft-point-absolute $tmp
) || exit $?

WVSTART "save --graft /x/y=/a/b (relative paths)"
(
    tmp=graft-points.tmp
    WVPASS force-delete $tmp
    WVPASS mkdir $tmp
    export BUP_DIR="$(WVPASS pwd)/$tmp/bup" || exit $?
    WVPASS bup init
    WVPASS mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save --graft $tmp/src=x -n foo $tmp/src
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/ "$tmp/restore/latest/$TOP/x/"
) || exit $?

WVSTART "save --graft /x/y=/a/b (matching structure)"
(
    tmp=graft-points.tmp
    WVPASS force-delete $tmp
    WVPASS mkdir $tmp
    export BUP_DIR="$(WVPASS pwd)/$tmp/bup" || exit $?
    WVPASS bup init
    WVPASS mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save -v --graft "$TOP/$tmp/src/x/y=$TOP/$tmp/src/a/b" \
        -n foo $tmp/src/x/y
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/x/y/ \
        "$tmp/restore/latest/$TOP/$tmp/src/a/b/"
) || exit $?

WVSTART "save --graft /x/y=/a (shorter target)"
(
    tmp=graft-points.tmp
    WVPASS force-delete $tmp
    WVPASS mkdir $tmp
    export BUP_DIR="$(WVPASS pwd)/$tmp/bup" || exit $?
    WVPASS bup init
    WVPASS mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save -v --graft "$TOP/$tmp/src/x/y=/a" -n foo $tmp/src/x/y
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/x/y/ "$tmp/restore/latest/a/"
) || exit $?

WVSTART "save --graft /x=/a/b (longer target)"
(
    tmp=graft-points.tmp
    export BUP_DIR="$(WVPASS pwd)/$tmp/bup" || exit $?
    WVPASS force-delete $tmp
    WVPASS mkdir $tmp
    WVPASS bup init
    WVPASS mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save -v --graft "$TOP/$tmp/src=$TOP/$tmp/src/a/b/c" \
        -n foo $tmp/src
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/ "$tmp/restore/latest/$TOP/$tmp/src/a/b/c/"
) || exit $?

WVSTART "save --graft /x=/ (root target)"
(
    tmp=graft-points.tmp
    export BUP_DIR="$(WVPASS pwd)/$tmp/bup" || exit $?
    WVPASS force-delete $tmp
    WVPASS mkdir $tmp
    WVPASS bup init
    WVPASS mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save -v --graft "$TOP/$tmp/src/x=/" -n foo $tmp/src/x
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/x/ "$tmp/restore/latest/"
) || exit $?

#WVSTART "save --graft /=/x/ (root source)"
# FIXME: Not tested for now -- will require cleverness, or caution as root.

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
WVPASSEQ "$(bup ls bupdir/latest/)" "a
b
c/"
WVPASS bup index -f $INDEXFILE --exclude=$D/c -ux $D
WVPASS bup save --strip -n indexfile -f $INDEXFILE $D
WVPASSEQ "$(bup ls indexfile/latest/)" "a
b"


WVSTART "import-rsnapshot"
D=rsnapshot.tmp
export BUP_DIR="$TOP/$D/.bup"
WVPASS force-delete $D
WVPASS mkdir $D
WVPASS bup init
WVPASS mkdir -p $D/hourly.0/buptest/a
WVPASS touch $D/hourly.0/buptest/a/b
WVPASS mkdir -p $D/hourly.0/buptest/c/d
WVPASS touch $D/hourly.0/buptest/c/d/e
WVPASS true
WVPASS bup import-rsnapshot $D/
WVPASSEQ "$(bup ls buptest/latest/)" "a/
c/"


if [ "$(type -p rdiff-backup)" != "" ]; then
    WVSTART "import-rdiff-backup"
    D=rdiff-backup.tmp
    export BUP_DIR="$TOP/$D/.bup"
    WVPASS force-delete $D
    WVPASS mkdir $D
    WVPASS bup init
    WVPASS mkdir $D/rdiff-backup
    WVPASS rdiff-backup $TOP/cmd $D/rdiff-backup
    WVPASS bup tick
    WVPASS rdiff-backup $TOP/Documentation $D/rdiff-backup
    WVPASS bup import-rdiff-backup $D/rdiff-backup import-rdiff-backup
    WVPASSEQ $(bup ls import-rdiff-backup/ | wc -l) 3
    WVPASSEQ "$(bup ls import-rdiff-backup/latest/ | sort)" "$(ls $TOP/Documentation | sort)"
fi


WVSTART "compression"
D=compression0.tmp
export BUP_DIR="$TOP/$D/.bup"
WVPASS force-delete $D
WVPASS mkdir $D
WVPASS bup init
WVPASS bup index $TOP/Documentation
WVPASS bup save -n compression -0 --strip $TOP/Documentation
# 'ls' on NetBSD sets -A by default when running as root, so we have to undo
# it by grepping out any dotfiles.  (Normal OSes don't auto-set -A, but this
# is harmless there.)
expected="$(WVPASS ls $TOP/Documentation | grep -v '^\.' | WVPASS sort)" \
    || exit $?
actual="$(WVPASS bup ls compression/latest/ | WVPASS sort)" || exit $?
WVPASSEQ "$actual" "$expected"
COMPRESSION_0_SIZE=$(WVPASS du -k -s $D | WVPASS cut -f1) || exit $?

D=compression9.tmp
export BUP_DIR="$TOP/$D/.bup"
WVPASS force-delete $D
WVPASS mkdir $D
WVPASS bup init
WVPASS bup index $TOP/Documentation
WVPASS bup save -n compression -9 --strip $TOP/Documentation
WVPASSEQ "$(bup ls compression/latest/ | sort)" \
         "$(ls $TOP/Documentation | grep -v '^\.' | sort)"
COMPRESSION_9_SIZE=$(WVPASS du -k -s $D | WVPASS cut -f1) || exit $?

WVPASS [ "$COMPRESSION_9_SIZE" -lt "$COMPRESSION_0_SIZE" ]

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
    tmpdir="$(WVPASS mktemp -d $real_tmp/bup-test-XXXXXXX)" || exit $?
    cleanup() { WVPASS rm -r "${tmpdir}"; }
    WVPASS trap cleanup EXIT
    WVPASS date > "$tmpdir/2"

    export BUP_DIR="$TOP/buptest.tmp"
    WVPASS test -d "$BUP_DIR" && WVPASS rm -r "$BUP_DIR"

    WVPASS bup init
    WVPASS bup index -vu $(pwd)/$D/x "$tmpdir"
    WVPASS bup save -t -n src $(pwd)/$D/x "$tmpdir"

    # For now, assume that "ls -a" and "sort" use the same order.
    actual="$(WVPASS bup ls -a src/latest)" || exit $?
    expected="$(echo -e "$pwd_top/\n$tmp_top/" | WVPASS sort)" || exit $?
    WVPASSEQ "$actual" "$expected"
) || exit $?

WVSTART "clear-index"
D=clear-index.tmp
export BUP_DIR="$TOP/$D/.bup"
WVPASS force-delete $TOP/$D
WVPASS mkdir $TOP/$D
WVPASS bup init
WVPASS touch $TOP/$D/foo
WVPASS touch $TOP/$D/bar
WVPASS bup index -u $D
WVPASSEQ "$(bup index -p)" "$D/foo
$D/bar
$D/
./"
WVPASS rm $TOP/$D/foo
WVPASS bup index --clear
WVPASS bup index -u $TOP/$D
expected="$(WVPASS bup index -p)" || exit $?
WVPASSEQ "$expected" "$D/bar
$D/
./"

# bup index --exclude-rx ...
(
    export BUP_DIR="$TOP/buptest.tmp"
    D=bupdata.tmp

    WVSTART "index --exclude-rx '^/foo' (root anchor)"
    WVPASS rm -rf "$D" "$BUP_DIR" buprestore.tmp
    WVPASS bup init
    WVPASS mkdir $D
    WVPASS touch $D/a
    WVPASS touch $D/b
    WVPASS mkdir $D/sub1
    WVPASS mkdir $D/sub2
    WVPASS touch $D/sub1/a
    WVPASS touch $D/sub2/b
    WVPASS bup index -u $D --exclude-rx "^$(pwd)/$D/sub1/"
    WVPASS bup save --strip -n bupdir $D
    WVPASS bup restore -C buprestore.tmp /bupdir/latest/
    actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
    WVPASSEQ "$actual" ".
./a
./b
./sub2
./sub2/b"

    WVSTART "index --exclude-rx '/foo$' (non-dir, tail anchor)"
    WVPASS rm -rf "$D" "$BUP_DIR" buprestore.tmp
    WVPASS bup init
    WVPASS mkdir $D
    WVPASS touch $D/a
    WVPASS touch $D/b
    WVPASS touch $D/foo
    WVPASS mkdir $D/sub
    WVPASS mkdir $D/sub/foo
    WVPASS touch $D/sub/foo/a
    WVPASS bup index -u $D --exclude-rx '/foo$'
    WVPASS bup save --strip -n bupdir $D
    WVPASS bup restore -C buprestore.tmp /bupdir/latest/
    actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
    WVPASSEQ "$actual" ".
./a
./b
./sub
./sub/foo
./sub/foo/a"

    WVSTART "index --exclude-rx '/foo/$' (dir, tail anchor)"
    WVPASS rm -rf "$D" "$BUP_DIR" buprestore.tmp
    WVPASS bup init
    WVPASS mkdir $D
    WVPASS touch $D/a
    WVPASS touch $D/b
    WVPASS touch $D/foo
    WVPASS mkdir $D/sub
    WVPASS mkdir $D/sub/foo
    WVPASS touch $D/sub/foo/a
    WVPASS bup index -u $D --exclude-rx '/foo/$'
    WVPASS bup save --strip -n bupdir $D
    WVPASS bup restore -C buprestore.tmp /bupdir/latest/
    actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
    WVPASSEQ "$actual" ".
./a
./b
./foo
./sub"

    WVSTART "index --exclude-rx '/foo/.' (dir content)"
    WVPASS rm -rf "$D" "$BUP_DIR" buprestore.tmp
    WVPASS bup init
    WVPASS mkdir $D
    WVPASS touch $D/a
    WVPASS touch $D/b
    WVPASS touch $D/foo
    WVPASS mkdir $D/sub
    WVPASS mkdir $D/sub/foo
    WVPASS touch $D/sub/foo/a
    WVPASS bup index -u $D --exclude-rx '/foo/.'
    WVPASS bup save --strip -n bupdir $D
    WVPASS bup restore -C buprestore.tmp /bupdir/latest/
    actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
    WVPASSEQ "$actual" ".
./a
./b
./foo
./sub
./sub/foo"
) || exit $?


# bup restore --exclude-rx ...
(
    export BUP_DIR="$TOP/buptest.tmp"
    D=bupdata.tmp

    WVSTART "restore --exclude-rx '^/foo' (root anchor)"
    WVPASS rm -rf "$D" "$BUP_DIR" buprestore.tmp
    WVPASS bup init
    WVPASS mkdir $D
    WVPASS touch $D/a
    WVPASS touch $D/b
    WVPASS mkdir $D/sub1
    WVPASS mkdir $D/sub2
    WVPASS touch $D/sub1/a
    WVPASS touch $D/sub2/b
    WVPASS bup index -u $D
    WVPASS bup save --strip -n bupdir $D
    WVPASS bup restore -C buprestore.tmp --exclude-rx "^/sub1/" /bupdir/latest/
    actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
    WVPASSEQ "$actual" ".
./a
./b
./sub2
./sub2/b"

    WVSTART "restore --exclude-rx '/foo$' (non-dir, tail anchor)"
    WVPASS rm -rf "$D" "$BUP_DIR" buprestore.tmp
    WVPASS bup init
    WVPASS mkdir $D
    WVPASS touch $D/a
    WVPASS touch $D/b
    WVPASS touch $D/foo
    WVPASS mkdir $D/sub
    WVPASS mkdir $D/sub/foo
    WVPASS touch $D/sub/foo/a
    WVPASS bup index -u $D
    WVPASS bup save --strip -n bupdir $D
    WVPASS bup restore -C buprestore.tmp --exclude-rx '/foo$' /bupdir/latest/
    actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
    WVPASSEQ "$actual" ".
./a
./b
./sub
./sub/foo
./sub/foo/a"

    WVSTART "restore --exclude-rx '/foo/$' (dir, tail anchor)"
    WVPASS rm -rf "$D" "$BUP_DIR" buprestore.tmp
    WVPASS bup init
    WVPASS mkdir $D
    WVPASS touch $D/a
    WVPASS touch $D/b
    WVPASS touch $D/foo
    WVPASS mkdir $D/sub
    WVPASS mkdir $D/sub/foo
    WVPASS touch $D/sub/foo/a
    WVPASS bup index -u $D
    WVPASS bup save --strip -n bupdir $D
    WVPASS bup restore -C buprestore.tmp --exclude-rx '/foo/$' /bupdir/latest/
    actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
    WVPASSEQ "$actual" ".
./a
./b
./foo
./sub"

    WVSTART "restore --exclude-rx '/foo/.' (dir content)"
    WVPASS rm -rf "$D" "$BUP_DIR" buprestore.tmp
    WVPASS bup init
    WVPASS mkdir $D
    WVPASS touch $D/a
    WVPASS touch $D/b
    WVPASS touch $D/foo
    WVPASS mkdir $D/sub
    WVPASS mkdir $D/sub/foo
    WVPASS touch $D/sub/foo/a
    WVPASS bup index -u $D
    WVPASS bup save --strip -n bupdir $D
    WVPASS bup restore -C buprestore.tmp --exclude-rx '/foo/.' /bupdir/latest/
    actual="$(WVPASS cd buprestore.tmp; WVPASS find . | WVPASS sort)" || exit $?
    WVPASSEQ "$actual" ".
./a
./b
./foo
./sub
./sub/foo"
) || exit $?
