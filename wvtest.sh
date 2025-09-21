#
# Include this file in your shell script by using:
#         #!/bin/sh
#         . ./wvtest.sh
#

# Here just because it's already sourced "everywhere".
export BUP_DIR=/dev/null
export GIT_DIR=/dev/null

# we don't quote $TEXT in case it contains newlines; newlines
# aren't allowed in test output.  However, we set -f so that
# at least shell glob characters aren't processed.
_wvtextclean()
{
	( set -f; echo $* )
}


if [ -n "$BASH_VERSION" ]; then
	. ./wvtest-bash.sh  # This keeps sh from choking on the syntax.
else
	_wvbacktrace() { true; }
	_wvpushcall() { true; }
	_wvpopcall() { true; }

	_wvfind_caller()
	{
		WVCALLER_FILE="unknown"
		WVCALLER_LINE=0
	}
fi


_wvcheck()
{
	local CODE="$1"
	local TEXT=$(_wvtextclean "$2")
	local OK=ok
	if [ "$CODE" -ne 0 ]; then
		OK=FAILED
	fi
	echo "! $WVCALLER_FILE:$WVCALLER_LINE  $TEXT  $OK" >&2
	if [ "$CODE" -ne 0 ]; then
		_wvbacktrace
		exit $CODE
	else
		return 0
	fi
}


WVEXPRC()
{
	if test $# -lt 2; then
		echo 'Usage: WVEXPRC RC_CASE_PATTERN COMMAND [ARG ...]'
		exit 2
	fi
	local exp="$1"
	shift
	local TEXT="$*"
	_wvpushcall "$@"

	_wvfind_caller
	case "$-" in
		*e*) set +e; "$@"; rc=$? ;;
		*) "$@"; rc=$? ;;
	esac
	case "$rc" in
		$exp)
			_wvcheck 0 "\$?=$rc matches $exp for $TEXT"
			_wvpopcall
			return 0
			;;
		*)
			_wvcheck 1 "\$?=$rc matches $exp for $TEXT"
			# NOTREACHED
			return 1
			;;
	esac
}


WVPASS()
{
	local TEXT="$*"
	_wvpushcall "$@"

	_wvfind_caller
	if "$@"; then
		_wvpopcall
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
	local TEXT="$*"
	_wvpushcall "$@"

	_wvfind_caller
	if "$@"; then
		_wvcheck 1 "NOT($TEXT)"
		# NOTREACHED
		return 1
	else
		_wvcheck 0 "NOT($TEXT)"
		_wvpopcall
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
	_wvpushcall "$@"
	_wvfind_caller
	_wvcheck $(_wvgetrv [ "$#" -eq 2 ]) "exactly 2 arguments"
	echo "Comparing:" >&2
	echo "$1" >&2
	echo "--" >&2
	echo "$2" >&2
	_wvcheck $(_wvgetrv [ "$1" = "$2" ]) "'$1' = '$2'"
	_wvpopcall
}


WVPASSNE()
{
	_wvpushcall "$@"
	_wvfind_caller
	_wvcheck $(_wvgetrv [ "$#" -eq 2 ]) "exactly 2 arguments"
	echo "Comparing:" >&2
	echo "$1" >&2
	echo "--" >&2
	echo "$2" >&2
	_wvcheck $(_wvgetrv [ "$1" != "$2" ]) "'$1' != '$2'"
	_wvpopcall
}


WVPASSRC()
{
	local RC=$?
	_wvpushcall "$@"
	_wvfind_caller
	_wvcheck $(_wvgetrv [ $RC -eq 0 ]) "return code($RC) == 0"
	_wvpopcall
}


WVFAILRC()
{
	local RC=$?
	_wvpushcall "$@"
	_wvfind_caller
	_wvcheck $(_wvgetrv [ $RC -ne 0 ]) "return code($RC) != 0"
	_wvpopcall
}


WVSTART()
{
	echo >&2
	_wvfind_caller
	echo "Testing \"$*\" in $WVCALLER_FILE:" >&2
}


WVSKIP()
{
	local TEXT=$(_wvtextclean "$@")
	_wvpushcall "$@"
	_wvfind_caller
	echo "! $WVCALLER_FILE:$WVCALLER_LINE  $TEXT  skip ok" 1>&2
}


WVDIE()
{
	local TEXT=$(_wvtextclean "$@")
	_wvpushcall "$@"
	_wvfind_caller
	echo "! $WVCALLER_FILE:$WVCALLER_LINE  $TEXT  FAILED" 1>&2
	exit 1
}


# Local Variables:
# indent-tabs-mode: t
# sh-basic-offset: 8
# End:
