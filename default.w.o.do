if [ -e "$1.c" ]; then
	CC=i586-mingw32msvc-gcc
	SRC=$1.c
elif [ -e "$1.cc" ]; then
	CC=i586-mingw32msvc-g++
	SRC=$1.cc
else
	echo "No such file: $1.c or $1.cc" >&2
	exit 1
fi
$CC -o $3 -Wall -g -O2 \
	-MD -MF "$1.wd" \
	-Ilib/bup \
	-Ibupdate/block-sha1 \
	-Ibupdate/wvcom \
	-c "$SRC"
read DEPS <$1.wd
rm -f "$1.wd"
DEPS=${DEPS#*:}
redo-ifchange "$SRC" $DEPS
