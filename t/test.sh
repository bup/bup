#!/usr/bin/env bash
. wvtest.sh
#set -e

TOP="$(pwd)"
export BUP_DIR="$TOP/buptest.tmp"

bup()
{
    "$TOP/bup" "$@"
}

WVSTART "init"

#set -x
rm -rf "$BUP_DIR"
WVPASS bup init

WVSTART "index"
D=bupdata.tmp
rm -rf $D
mkdir $D
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
"A $D/f
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
"A $D/f
M $D/d/z
  $D/d/e/
M $D/d/
  $D/b
  $D/a
A $D/"

WVPASS bup index -u $D/d/e $D/a --fake-invalid
WVPASSEQ "$(cd $D && bup index -m .)" \
"./f
./d/z
./d/e/
./d/
./a
./"
WVPASSEQ "$(cd $D && bup index -m)" \
"f
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
WVFAIL bup save -t $D/d/e/fifotest
WVFAIL bup save -t $D/d/e
rm -f $D/d/e/fifotest
WVPASS bup index -u $D/d/e
WVFAIL bup save -t $D/d/e/fifotest
mv $BUP_DIR/bi.old $BUP_DIR/bupindex

WVPASS bup index -u $D/d/e
WVPASS bup save -t $D/d/e
WVPASSEQ "$(cd $D && bup index -m)" \
"f
d/z
d/
a
./"
WVPASS bup save -t $D/d
WVPASSEQ "$(cd $D && bup index -m)" \
"f
a
./"
tree1=$(bup save -t $D)
WVPASSEQ "$(cd $D && bup index -m)" ""
tree2=$(bup save -t $D)
WVPASSEQ "$tree1" "$tree2"
WVPASSEQ "$(bup index -s / | grep ^D)" ""
tree3=$(bup save -t /)
WVPASSEQ "$tree1" "$tree3"

WVSTART "split"
WVPASS bup split --bench -b <t/testfile1 >tags1.tmp
WVPASS bup split -vvvv -b t/testfile2 >tags2.tmp
WVPASS bup margin
WVPASS bup midx -f
WVPASS bup margin
WVPASS bup split -t t/testfile2 >tags2t.tmp
WVPASS bup split -t t/testfile2 --fanout 3 >tags2tf.tmp
WVPASS bup split -r "$BUP_DIR" -c t/testfile2 >tags2c.tmp
WVPASS ls -lR \
   | WVPASS bup split -r "$BUP_DIR" -c --fanout 3 --max-pack-objects 3 -n lslr
WVPASS bup ls
WVFAIL bup ls /does-not-exist
WVPASS bup ls /lslr
#WVPASS bup ls /lslr/1971-01-01   # all dates always exist
WVFAIL diff -u tags1.tmp tags2.tmp

# fanout must be different from non-fanout
WVFAIL diff -q tags2t.tmp tags2tf.tmp
wc -c t/testfile1 t/testfile2
wc -l tags1.tmp tags2.tmp

WVPASS bup memtest -c1 -n100
WVPASS bup memtest -c1 -n100 --existing

WVSTART "join"
WVPASS bup join $(cat tags1.tmp) >out1.tmp
WVPASS bup join <tags2.tmp >out2.tmp
WVPASS bup join <tags2t.tmp >out2t.tmp
WVPASS bup join -r "$BUP_DIR" <tags2c.tmp >out2c.tmp
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
	  egrep -v 'dangling (commit|tree)' |
	  tee -a /dev/stderr | 
	  wc -l)
    WVPASS [ "$n" -eq 0 ]
) || exit 1

WVSTART "restore"
rm -rf buprestore.tmp
WVFAIL bup restore boink
WVPASS bup restore -C buprestore.tmp "/master/latest/$TOP/$D"
WVPASSEQ "$(ls buprestore.tmp)" "bupdata.tmp"
rm -rf buprestore.tmp
WVPASS bup restore -C buprestore.tmp "/master/latest/$TOP/$D/"
WVPASS diff -ur $D/ buprestore.tmp/

WVSTART "ftp"
WVPASS bup ftp "cat /master/latest/$TOP/$D/b" >$D/b.new
WVPASS bup ftp "cat /master/latest/$TOP/$D/f" >$D/f.new
WVPASS bup ftp "cat /master/latest/$TOP/$D/f"{,} >$D/f2.new
WVPASS bup ftp "cat /master/latest/$TOP/$D/a" >$D/a.new
WVPASSEQ "$(sha1sum <$D/b)" "$(sha1sum <$D/b.new)"
WVPASSEQ "$(sha1sum <$D/f)" "$(sha1sum <$D/f.new)"
WVPASSEQ "$(cat $D/f.new{,} | sha1sum)" "$(sha1sum <$D/f2.new)"
WVPASSEQ "$(sha1sum <$D/a)" "$(sha1sum <$D/a.new)"

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
