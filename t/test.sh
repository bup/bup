#!/bin/bash
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
touch $D/a $D/b $D/f
mkdir $D/d $D/d/e
WVPASSEQ "$(bup index -s $D/)" "A $D/"
WVPASSEQ "$(bup index -s $D/b)" ""
bup tick
WVPASSEQ "$(bup index --check -us $D/b)" "A $D/b"
WVPASSEQ "$(bup index --check -us $D/b $D/d)" \
"A $D/d/e/
A $D/d/
A $D/b"
touch $D/d/z
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
touch $D/a
WVPASS bup index -u $D/a  # becomes modified
WVPASSEQ "$(bup index -s $D/a $D $D/b)" \
"A $D/f
A $D/d/z
A $D/d/e/
A $D/d/
  $D/b
M $D/a
A $D/"

# FIXME: currently directories are never marked unmodified, so -m just skips
# them.  Eventually, we should actually store the hashes of completed
# directories, at which time the output of -m will change, so we'll have to
# change this test too.
WVPASSEQ "$(cd $D && bup index -m .)" \
"./f
./d/z
./a"
WVPASSEQ "$(cd $D && bup index -m)" \
"f
d/z
a"
WVPASSEQ "$(cd $D && bup index -s .)" "$(cd $D && bup index -s .)"


WVSTART "split"
WVPASS bup split --bench -b <t/testfile1 >tags1.tmp
WVPASS bup split -vvvv -b t/testfile2 >tags2.tmp
WVPASS bup midx -a
WVPASS bup split -t t/testfile2 >tags2t.tmp
WVPASS bup split -t t/testfile2 --fanout 3 >tags2tf.tmp
WVPASS bup split -r "$BUP_DIR" -c t/testfile2 >tags2c.tmp
WVPASS ls -lR \
   | WVPASS bup split -r "$BUP_DIR" -c --fanout 3 --max-pack-objects 3 -n lslr
WVPASS bup ls
WVFAIL bup ls /does-not-exist
WVPASS bup ls /lslr
WVPASS bup ls /lslr/1971-01-01   # all dates always exist
WVFAIL diff -u tags1.tmp tags2.tmp

# fanout must be different from non-fanout
WVFAIL diff -q tags2t.tmp tags2tf.tmp
wc -c t/testfile1 t/testfile2
wc -l tags1.tmp tags2.tmp

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

WVSTART "fsck"
WVPASS bup fsck
if bup fsck --par2-ok; then
    WVSTART "fsck (par2)"
else
    WVSTART "fsck (PAR2 IS MISSING)"
fi
WVPASS bup fsck -g
WVPASS bup fsck -r
WVPASS bup damage $BUP_DIR/objects/pack/*.pack -n10 -s1 -S0
WVFAIL bup fsck
WVFAIL bup fsck --disable-par2
chmod u+w $BUP_DIR/objects/pack/*.idx
WVPASS bup damage $BUP_DIR/objects/pack/*.idx -n10 -s1 -S0
WVFAIL bup fsck -j4
WVPASS bup damage $BUP_DIR/objects/pack/*.pack -n10 -s1024 --percent 0.4 -S0
WVFAIL bup fsck
WVFAIL bup fsck -rvv -j99   # fails because repairs were needed
if bup fsck --par2-ok; then
    WVPASS bup fsck -r # ok because of repairs from last time
    WVPASS bup damage $BUP_DIR/objects/pack/*.pack -n201 -s1 --equal -S0
    WVFAIL bup fsck
    WVFAIL bup fsck -rvv   # too many errors to be repairable
    WVFAIL bup fsck -r   # too many errors to be repairable
else
    WVFAIL bup fsck -r # still fails because par2 was missing
fi
