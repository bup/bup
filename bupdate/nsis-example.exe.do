BASE=${1%.exe}
redo-ifchange nsis-example.nsi bupdate.dll
exec >&2
if ! makensis $BASE.nsi >$1.err 2>&1; then
	cat $1.err >&2
	exit 1
fi
mv $BASE-new.exe $3
