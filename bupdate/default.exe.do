[ -e "${1}_main.c" ] && MAIN=${1}_main.w.o || MAIN=
. ./link.exe.od "$3" \
	$1.w.o $MAIN \
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
	