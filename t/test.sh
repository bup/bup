#!/usr/bin/env bash
. wvtest.sh
#set -e

TOP="$(/bin/pwd)"
export BUP_DIR="$TOP/buptest.tmp"

bup()
{
    "$TOP/bup" "$@"
}

force-delete()
{
    chmod -R u+w "$@"
    for f in "$@"; do
        test -e "$@" || continue
        chattr -fR = "$@" || true
        setfacl -Rb "$@"
        rm -r "$@"
    done
}

WVSTART "init"

#set -x
test -d "$BUP_DIR" && rm -r "$BUP_DIR"
WVPASS bup init

WVSTART "index"
D=bupdata.tmp
force-delete $D
mkdir $D
WVFAIL bup index --exclude-from $D/cannot-exist $D
WVPASSEQ "$(bup index --check -p)" ""
WVPASSEQ "$(bup index --check -p $D)" ""
WVFAIL [ -e $D.fake ]
WVFAIL bup index --check -u $D.fake
WVPASS bup index --check -u $D
WVPASSEQ "$(bup index --check -p $D)" "$D/"
touch $D/a
WVPASS bup random 128k >$D/b
mkdir $D/d $D/d/e
WVPASS bup random 512 >$D/f
WVPASS ln -s non-existent-file $D/g
WVPASSEQ "$(bup index -s $D/)" "A $D/"
WVPASSEQ "$(bup index -s $D/b)" ""
WVPASSEQ "$(bup index --check -us $D/b)" "A $D/b"
WVPASSEQ "$(bup index --check -us $D/b $D/d)" \
"A $D/d/e/
A $D/d/
A $D/b"
touch $D/d/z
bup tick
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
touch $D/d/z
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

mv $BUP_DIR/bupindex $BUP_DIR/bi.old
WVFAIL bup save -t $D/d/e/fifotest
mkfifo $D/d/e/fifotest
WVPASS bup index -u $D/d/e/fifotest
WVPASS bup save -t $D/d/e/fifotest
WVPASS bup save -t $D/d/e
rm -f $D/d/e/fifotest
WVPASS bup index -u $D/d/e
WVFAIL bup save -t $D/d/e/fifotest
mv $BUP_DIR/bi.old $BUP_DIR/bupindex

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
tree1=$(bup save -t $D) || WVFAIL
WVPASSEQ "$(cd $D && bup index -m)" ""
tree2=$(bup save -t $D) || WVFAIL
WVPASSEQ "$tree1" "$tree2"
WVPASSEQ "$(bup index -s / | grep ^D)" ""
tree3=$(bup save -t /) || WVFAIL
WVPASSEQ "$tree1" "$tree3"
WVPASS bup save -r :$BUP_DIR -n r-test $D
WVFAIL bup save -r :$BUP_DIR/fake/path -n r-test $D
WVFAIL bup save -r :$BUP_DIR -n r-test $D/fake/path

WVSTART "split"
echo a >a.tmp
echo b >b.tmp
WVPASS bup split -b a.tmp >taga.tmp
WVPASS bup split -b b.tmp >tagb.tmp
cat a.tmp b.tmp | WVPASS bup split -b >tagab.tmp
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
bup tick
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
   | WVPASS bup split -r :$BUP_DIR -c --fanout 3 --max-pack-objects 3 -n lslr
WVPASS bup ls
WVFAIL bup ls /does-not-exist
WVPASS bup ls /lslr
WVPASS bup ls /lslr/latest
WVPASS bup ls /lslr/latest/
#WVPASS bup ls /lslr/1971-01-01   # all dates always exist
WVFAIL diff -u tags1.tmp tags2.tmp

# fanout must be different from non-fanout
WVFAIL diff tags2t.tmp tags2tf.tmp
wc -c t/testfile1 t/testfile2
wc -l tags1.tmp tags2.tmp

WVSTART "bloom"
WVPASS bup bloom -c $(ls -1 $BUP_DIR/objects/pack/*.idx|head -n1)
rm $BUP_DIR/objects/pack/bup.bloom
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
    set -e
    cd "$BUP_DIR" || exit 1
    #git repack -Ad
    #git prune
    (cd "$TOP/t/sampledata" && WVPASS bup save -vvn master /) || WVFAIL
    n=$(git fsck --full --strict 2>&1 | 
      egrep -v 'dangling (commit|tree|blob)' |
      tee -a /dev/stderr | 
      wc -l)
    WVPASS [ "$n" -eq 0 ]
) || exit 1

WVSTART "restore"
force-delete buprestore.tmp
WVFAIL bup restore boink
touch $TOP/$D/$D
bup index -u $TOP/$D
bup save -n master /
WVPASS bup restore -C buprestore.tmp "/master/latest/$TOP/$D"
WVPASSEQ "$(ls buprestore.tmp)" "bupdata.tmp"
force-delete buprestore.tmp
WVPASS bup restore -C buprestore.tmp "/master/latest/$TOP/$D/"
touch $D/non-existent-file buprestore.tmp/non-existent-file # else diff fails
WVPASS diff -ur $D/ buprestore.tmp/

(
    tmp=testrestore.tmp
    force-delete $tmp
    mkdir $tmp
    export BUP_DIR="$(pwd)/$tmp/bup"
    WVPASS bup init
    mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save --strip -n foo $tmp/src

    WVSTART "restore /foo/latest"
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/ $tmp/restore/latest/

    WVSTART "restore /foo/latest/"
    force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/
    for x in $tmp/src/*; do
        WVPASS t/compare-trees $x/ $tmp/restore/$(basename $x);
    done

    WVSTART "restore /foo/latest/."
    force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/.
    WVPASS t/compare-trees $tmp/src/ $tmp/restore/

    WVSTART "restore /foo/latest/x"
    force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/x
    WVPASS t/compare-trees $tmp/src/x/ $tmp/restore/x/

    WVSTART "restore /foo/latest/x/"
    force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/x/
    for x in $tmp/src/x/*; do
        WVPASS t/compare-trees $x/ $tmp/restore/$(basename $x);
    done

    WVSTART "restore /foo/latest/x/."
    force-delete "$tmp/restore"
    WVPASS bup restore -C $tmp/restore /foo/latest/x/.
    WVPASS t/compare-trees $tmp/src/x/ $tmp/restore/
) || WVFAIL


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
chmod u+w $BUP_DIR/objects/pack/*.idx
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
force-delete $D
mkdir $D
export BUP_DIR="$D/.bup"
WVPASS bup init
touch $D/a
WVPASS bup random 128k >$D/b
mkdir $D/d $D/d/e
WVPASS bup random 512 >$D/f
WVPASS bup index -ux $D
bup save -n exclude-bupdir $D
WVPASSEQ "$(bup ls -a exclude-bupdir/latest/$TOP/$D/)" "a
b
d/
f"

WVSTART "exclude"
D=exclude.tmp
force-delete $D
mkdir $D
export BUP_DIR="$D/.bup"
WVPASS bup init
touch $D/a
WVPASS bup random 128k >$D/b
mkdir $D/d $D/d/e
WVPASS bup random 512 >$D/f
WVPASS bup index -ux --exclude $D/d $D
bup save -n exclude $D
WVPASSEQ "$(bup ls exclude/latest/$TOP/$D/)" "a
b
f"
mkdir $D/g $D/h
WVPASS bup index -ux --exclude $D/d --exclude $TOP/$D/g --exclude $D/h $D
bup save -n exclude $D
WVPASSEQ "$(bup ls exclude/latest/$TOP/$D/)" "a
b
f"

WVSTART "exclude-from"
D=exclude-fromdir.tmp
EXCLUDE_FILE=exclude-from.tmp
echo "$D/d 
 $TOP/$D/g
$D/h" > $EXCLUDE_FILE
force-delete $D
mkdir $D
export BUP_DIR="$D/.bup"
WVPASS bup init
touch $D/a
WVPASS bup random 128k >$D/b
mkdir $D/d $D/d/e
WVPASS bup random 512 >$D/f
mkdir $D/g $D/h
WVPASS bup index -ux --exclude-from $EXCLUDE_FILE $D
bup save -n exclude-from $D
WVPASSEQ "$(bup ls exclude-from/latest/$TOP/$D/)" "a
b
f"
rm $EXCLUDE_FILE


WVSTART "save --strip"
(
    tmp=graft-points.tmp
    force-delete $tmp
    mkdir $tmp
    export BUP_DIR="$(pwd)/$tmp/bup"
    WVPASS bup init
    mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save --strip -n foo $tmp/src/x/y
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/x/y/ "$tmp/restore/latest/"
) || WVFAIL

WVSTART "save --strip-path (relative)"
(
    tmp=graft-points.tmp
    force-delete $tmp
    mkdir $tmp
    export BUP_DIR="$(pwd)/$tmp/bup"
    WVPASS bup init
    mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save --strip-path $tmp/src -n foo $tmp/src/x
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/ "$tmp/restore/latest/"
) || WVFAIL

WVSTART "save --strip-path (absolute)"
(
    tmp=graft-points.tmp
    force-delete $tmp
    mkdir $tmp
    export BUP_DIR="$(pwd)/$tmp/bup"
    WVPASS bup init
    mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save --strip-path "$TOP" -n foo $tmp/src
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/ "$tmp/restore/latest/$tmp/src/"
) || WVFAIL

WVSTART "save --strip-path (no match)"
(
    tmp=graft-points.tmp
    force-delete $tmp
    mkdir $tmp
    export BUP_DIR="$(pwd)/$tmp/bup"
    WVPASS bup init
    mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save --strip-path $tmp/foo -n foo $tmp/src/x
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/ "$tmp/restore/latest/$TOP/$tmp/src/"
) || WVFAIL

WVSTART "save --graft (empty graft points disallowed)"
(
    tmp=graft-points.tmp
    force-delete $tmp
    mkdir $tmp
    export BUP_DIR="$(pwd)/$tmp/bup"
    WVPASS bup init
    WVFAIL bup save --graft =/grafted -n graft-point-absolute $tmp
    WVFAIL bup save --graft $TOP/$tmp= -n graft-point-absolute $tmp
) || WVFAIL

WVSTART "save --graft /x/y=/a/b (relative paths)"
(
    tmp=graft-points.tmp
    force-delete $tmp
    mkdir $tmp
    export BUP_DIR="$(pwd)/$tmp/bup"
    WVPASS bup init
    mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save --graft $tmp/src=x -n foo $tmp/src
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/ "$tmp/restore/latest/$TOP/x/"
) || WVFAIL

WVSTART "save --graft /x/y=/a/b (matching structure)"
(
    tmp=graft-points.tmp
    force-delete $tmp
    mkdir $tmp
    export BUP_DIR="$(pwd)/$tmp/bup"
    WVPASS bup init
    mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save -v --graft "$TOP/$tmp/src/x/y=$TOP/$tmp/src/a/b" \
        -n foo $tmp/src/x/y
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/x/y/ \
        "$tmp/restore/latest/$TOP/$tmp/src/a/b/"
) || WVFAIL

WVSTART "save --graft /x/y=/a (shorter target)"
(
    tmp=graft-points.tmp
    force-delete $tmp
    mkdir $tmp
    export BUP_DIR="$(pwd)/$tmp/bup"
    WVPASS bup init
    mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save -v --graft "$TOP/$tmp/src/x/y=/a" -n foo $tmp/src/x/y
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/x/y/ "$tmp/restore/latest/a/"
) || WVFAIL

WVSTART "save --graft /x=/a/b (longer target)"
(
    tmp=graft-points.tmp
    export BUP_DIR="$(pwd)/$tmp/bup"
    force-delete $tmp
    mkdir $tmp
    WVPASS bup init
    mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save -v --graft "$TOP/$tmp/src=$TOP/$tmp/src/a/b/c" \
        -n foo $tmp/src
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/ "$tmp/restore/latest/$TOP/$tmp/src/a/b/c/"
) || WVFAIL

WVSTART "save --graft /x=/ (root target)"
(
    tmp=graft-points.tmp
    export BUP_DIR="$(pwd)/$tmp/bup"
    force-delete $tmp
    mkdir $tmp
    WVPASS bup init
    mkdir -p $tmp/src/x/y/z
    WVPASS bup random 8k > $tmp/src/x/y/random-1
    WVPASS bup random 8k > $tmp/src/x/y/z/random-2
    WVPASS bup index -u $tmp/src
    WVPASS bup save -v --graft "$TOP/$tmp/src/x=/" -n foo $tmp/src/x
    WVPASS bup restore -C $tmp/restore /foo/latest
    WVPASS t/compare-trees $tmp/src/x/ "$tmp/restore/latest/"
) || WVFAIL

#WVSTART "save --graft /=/x/ (root source)"
# FIXME: Not tested for now -- will require cleverness, or caution as root.

WVSTART "indexfile"
D=indexfile.tmp
INDEXFILE=tmpindexfile.tmp
rm -f $INDEXFILE
force-delete $D
mkdir $D
export BUP_DIR="$D/.bup"
WVPASS bup init
touch $D/a
touch $D/b
mkdir $D/c
WVPASS bup index -ux $D
bup save --strip -n bupdir $D
WVPASSEQ "$(bup ls bupdir/latest/)" "a
b
c/"
WVPASS bup index -f $INDEXFILE --exclude=$D/c -ux $D
bup save --strip -n indexfile -f $INDEXFILE $D
WVPASSEQ "$(bup ls indexfile/latest/)" "a
b"


WVSTART "import-rsnapshot"
D=rsnapshot.tmp
export BUP_DIR="$TOP/$D/.bup"
force-delete $D
mkdir $D
WVPASS bup init
mkdir -p $D/hourly.0/buptest/a
touch $D/hourly.0/buptest/a/b
mkdir -p $D/hourly.0/buptest/c/d
touch $D/hourly.0/buptest/c/d/e
WVPASS true
WVPASS bup import-rsnapshot $D/
WVPASSEQ "$(bup ls buptest/latest/)" "a/
c/"


if [ "$(which rdiff-backup)" != "" ]; then
    WVSTART "import-rdiff-backup"
    D=rdiff-backup.tmp
    export BUP_DIR="$TOP/$D/.bup"
    force-delete $D
    mkdir $D
    WVPASS bup init
    mkdir $D/rdiff-backup
    rdiff-backup $TOP/cmd $D/rdiff-backup
    bup tick
    rdiff-backup $TOP/Documentation $D/rdiff-backup
    WVPASS bup import-rdiff-backup $D/rdiff-backup import-rdiff-backup
    WVPASSEQ "$(bup ls import-rdiff-backup/ | wc -l)" "3"
    WVPASSEQ "$(bup ls import-rdiff-backup/latest/ | sort)" "$(ls $TOP/Documentation | sort)"
fi


WVSTART "compression"
D=compression0.tmp
export BUP_DIR="$TOP/$D/.bup"
force-delete $D
mkdir $D
WVPASS bup init
WVPASS bup index $TOP/Documentation
WVPASS bup save -n compression -0 --strip $TOP/Documentation
# 'ls' on NetBSD sets -A by default when running as root, so we have to undo
# it by grepping out any dotfiles.  (Normal OSes don't auto-set -A, but this
# is harmless there.)
WVPASSEQ "$(bup ls compression/latest/ | sort)" \
	 "$(ls $TOP/Documentation | grep -v '^\.' | sort)"
COMPRESSION_0_SIZE=$(du -k -s $D | cut -f1)

D=compression9.tmp
export BUP_DIR="$TOP/$D/.bup"
force-delete $D
mkdir $D
WVPASS bup init
WVPASS bup index $TOP/Documentation
WVPASS bup save -n compression -9 --strip $TOP/Documentation
WVPASSEQ "$(bup ls compression/latest/ | sort)" "$(ls $TOP/Documentation | sort)"
COMPRESSION_9_SIZE=$(du -k -s $D | cut -f1)

WVPASS [ "$COMPRESSION_9_SIZE" -lt "$COMPRESSION_0_SIZE" ]


WVSTART "save disjoint top-level directories"
(
    set -e
    top_dir="$(echo $(pwd) | awk -F "/" '{print $2}')"
    if [ "$top_dir" == tmp ]; then
        echo "(running from within /tmp; skipping test)"
        exit 0
    fi
    D=bupdata.tmp
    force-delete $D
    mkdir -p $D/x
    date > $D/x/1
    tmpdir="$(mktemp -d /tmp/bup-test-XXXXXXX)"
    cleanup() { set -x; rm -r "${tmpdir}"; set +x; }
    trap cleanup EXIT
    date > "$tmpdir/2"

    export BUP_DIR="$TOP/buptest.tmp"
    test -d "$BUP_DIR" && rm -r "$BUP_DIR"

    WVPASS bup init
    WVPASS bup index -vu $(pwd)/$D/x "$tmpdir"
    WVPASS bup save -t -n src $(pwd)/$D/x "$tmpdir"
    # For now, assume that "ls -a" and "sort" use the same order.
    WVPASSEQ "$(bup ls -a src/latest)" "$(echo -e "$top_dir/\ntmp/" | sort)"
) || WVFAIL


WVSTART "clear-index"
D=clear-index.tmp
export BUP_DIR="$TOP/$D/.bup"
force-delete $TOP/$D
mkdir $TOP/$D
WVPASS bup init
touch $TOP/$D/foo
touch $TOP/$D/bar
bup index -u $D
WVPASSEQ "$(bup index -p)" "$D/foo
$D/bar
$D/
./"
rm $TOP/$D/foo
WVPASS bup index --clear
bup index -u $TOP/$D
WVPASSEQ "$(bup index -p)" "$D/bar
$D/
./"
