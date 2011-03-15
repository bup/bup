[ -e "${1}_main.c" ] && MAIN=${1}_main.o || MAIN=
. ./link.od "$3" \
	$1.o $MAIN \
	http-curl.o \
	../lib/bup/bupsplit.o \
	block-sha1/sha1.o \
	wvcom/wvstring.o \
	wvcom/wverror.o \
	wvcom/wvcomstatus.o \
	wvcom/wvstringlist.o \
	wvcom/wvlinklist.o \
	wvcom/wvbuffer.o \
	wvcom/wvbufferstore.o \
	wvcom/wvstrutils.o \
	wvcom/wvdiriter.o \
