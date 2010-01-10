# we don't quote $TEXT in case it contains newlines; newlines
# aren't allowed in test output.  However, we set -f so that
# at least shell glob characters aren't processed.
_textclean()
{
	( set -f; echo $* )
}

_wvcheck()
{
	CODE="$1"
	TEXT=$(_textclean "$2")
	OK=ok
	if [ "$CODE" -ne 0 ]; then
		OK=FAILED
	fi
	echo "! ${BASH_SOURCE[2]}:${BASH_LINENO[1]}  $TEXT  $OK" >&2
	if [ "$CODE" -ne 0 ]; then
		exit $CODE
	else
		return 0
	fi
}


WVPASS()
{
	TEXT="$*"
	
	if "$@"; then
		_wvcheck 0 "$TEXT"
		return 0
	else
		_wvcheck 1 "$TEXT"
		# NOTREACHED
		return 1
	fi
}


WVFAIL()
{
	TEXT="$*"
	
	if "$@"; then
		_wvcheck 1 "NOT($TEXT)"
		# NOTREACHED
		return 1
	else
		_wvcheck 0 "NOT($TEXT)"
		return 0
	fi
}


_wvgetrv()
{
	( "$@" >&2 )
	echo -n $?
}


WVPASSEQ()
{
	WVPASS [ "$#" -eq 2 ]
	echo "Comparing:" >&2
	echo "$1" >&2
	echo "--" >&2
	echo "$2" >&2
	_wvcheck $(_wvgetrv [ "$1" = "$2" ]) "'$1' = '$2'"
}


WVPASSNE()
{
	WVPASS [ "$#" -eq 2 ]
	echo "Comparing:" >&2
	echo "$1" >&2
	echo "--" >&2
	echo "$2" >&2
	_wvcheck $(_wvgetrv [ "$1" != "$2" ]) "'$1' != '$2'"
}


WVSTART()
{
	echo >&2
	echo "Testing \"$*\" in ${BASH_SOURCE[1]}:" >&2
}
