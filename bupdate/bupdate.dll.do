exec >&2
TARGET=${1%.dll}
. ./dll.od "$TARGET" "$3" \
	$TARGET.w.o \
	nsis.w.o \
	http-win.w.o \
	../lib/bup/bupsplit.w.o \
	block-sha1/sha1.w.o \
	wvcom/wvstring.w.o \
	wvcom/wverror.w.o \
	wvcom/wvcom.w.o \
	wvcom/wvvariant.w.o \
	wvcom/wvcomstring.w.o \
	wvcom/wvcomstatus.w.o \
	wvcom/wvstringlist.w.o \
	wvcom/wvlinklist.w.o \
	wvcom/wvbuffer.w.o \
	wvcom/wvbufferstore.w.o \
	wvcom/wvstrutils.w.o \
	wvcom/wvdiriter.w.o \
