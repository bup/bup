redo-ifchange $1.c
i586-mingw32msvc-gcc -o $3 -Wall -g -O2 \
	-MD -MF $1.wd \
	-Ilib/bup \
	-Ibupdate/block-sha1 \
	-c $1.c
read DEPS <$1.wd
rm -f $1.wd
DEPS=${DEPS#*:}
redo-ifchange $DEPS
