#
# Include this file in your shell script by using:
#         #!/bin/sh
#         . ./wvtest.sh
#

# we don't quote $TEXT in case it contains newlines; newlines
# aren't allowed in test output.  However, we set -f so that
# at least shell glob characters aren't processed.
_wvtextclean()
{
	( set -f; echo $* )
}


if [ -n "$BASH_VERSION" ]; then
	_wvfind_caller()
	{
		WVCALLER_FILE=${BASH_SOURCE[2]}
		WVCALLER_LINE=${BASH_LINENO[1]}
	}
else
	_wvfind_caller()
	{
		WVCALLER_FILE="unknown"
		WVCALLER_LINE=0
	}
fi


_wvcheck()
{
	CODE="$1"
	TEXT=$(_wvtextclean "$2")
	OK=ok
	if [ "$CODE" -ne 0 ]; then
		OK=FAILED
	fi
	echo "! $WVCALLER_FILE:$WVCALLER_LINE  $TEXT  $OK" >&2
	if [ "$CODE" -ne 0 ]; then
		exit $CODE
	else
		return 0
	fi
}


WVPASS()
{
	TEXT="$*"

	_wvfind_caller
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

	_wvfind_caller
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
	_wvfind_caller
	_wvcheck $(_wvgetrv [ "$#" -eq 2 ]) "exactly 2 arguments"
	echo "Comparing:" >&2
	echo "$1" >&2
	echo "--" >&2
	echo "$2" >&2
	_wvcheck $(_wvgetrv [ "$1" = "$2" ]) "'$1' = '$2'"
}


WVPASSNE()
{
	_wvfind_caller
	_wvcheck $(_wvgetrv [ "$#" -eq 2 ]) "exactly 2 arguments"
	echo "Comparing:" >&2
	echo "$1" >&2
	echo "--" >&2
	echo "$2" >&2
	_wvcheck $(_wvgetrv [ "$1" != "$2" ]) "'$1' != '$2'"
}


WVPASSRC()
{
	RC=$?
	_wvfind_caller
	_wvcheck $(_wvgetrv [ $RC -eq 0 ]) "return code($RC) == 0"
}


WVFAILRC()
{
	RC=$?
	_wvfind_caller
	_wvcheck $(_wvgetrv [ $RC -ne 0 ]) "return code($RC) != 0"
}


WVSTART()
{
	echo >&2
	_wvfind_caller
	echo "Testing \"$*\" in $WVCALLER_FILE:" >&2
}
