exec >&2
[ -e "${1}_main.c" ] && MAIN=${1}_main.w.o || MAIN=
. ./link.exe.od "$3" \
	$MAIN \
	bupdate.dll
