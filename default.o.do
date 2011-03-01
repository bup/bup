redo-ifchange $1.c
gcc -o $3 -Wall -g -O2 \
	-MD -MF $1.d \
	-Ilib/bup \
	-Ibupdate/block-sha1 \
	-c $1.c
read DEPS <$1.d
rm -f $1.d
DEPS=${DEPS#*:}
redo-ifchange $DEPS
