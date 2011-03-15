if [ -e "$1.c" ]; then
	CC=gcc
	SRC=$1.c
elif [ -e "$1.cc" ]; then
	CC=g++
	SRC=$1.cc
else
	echo "No such file: $1.c or $1.cc" >&2
	exit 1
fi
$CC -o $3 -Wall -g -O2 \
	-MD -MF "$1.d" \
	-D_FILE_OFFSET_BITS=64 \
	-Ilib/bup \
	-Ibupdate/block-sha1 \
	-Ibupdate/wvcom \
	-c "$SRC"
read DEPS <$1.d
rm -f "$1.d"
DEPS=${DEPS#*:}
redo-ifchange "$SRC" $DEPS
