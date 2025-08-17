
declare -a _wvbtstack

_wvpushcall()
{
    _wvbtstack[${#_wvbtstack[@]}]="$*"
}

_wvpopcall()
{
    unset _wvbtstack[$((${#_wvbtstack[@]} - 1))]
}

_wvbacktrace()
{
    local i loc
    local call=$((${#_wvbtstack[@]} - 1))
    for ((i=0; i <= ${#FUNCNAME[@]}; i++)); do
	local name="${FUNCNAME[$i]}"
	if test "${name:0:2}" == WV; then
            loc="${BASH_SOURCE[$i+1]}:${BASH_LINENO[$i]}"
	    echo "called from $loc ${FUNCNAME[$i]} ${_wvbtstack[$call]}" 1>&2
	    ((call--))
	fi
    done
}

_wvfind_caller()
{
    WVCALLER_FILE=${BASH_SOURCE[2]}
    WVCALLER_LINE=${BASH_LINENO[1]}
}


_wvsigpipe_rc="$(dev/python -c 'import signal; print(signal.SIGPIPE.value)')" \
    || exit $?
_wvsigpipe_rc="$((_wvsigpipe_rc + 128))" || exit $?

WVPIPE()
{
    # Identical to WVPASS, except that it ignores SIGPIPE. For use
    # when the consumer might exit early, e.g. for coreutils head:
    #   WVPIPE something | WVPASS head -1
    local TEXT="$*"
    _wvpushcall "$@"

    _wvfind_caller
    "$@"
    local rc=$?
    if test $rc -eq 0 -o $rc -eq "$_wvsigpipe_rc"; then
	if test $rc -eq "$_wvsigpipe_rc"; then
	    TEXT="$TEXT (SIGPIPE)"
	fi
	_wvpopcall
	_wvcheck 0 "$TEXT"
	return 0
    else
	_wvcheck 1 "$TEXT"
	# NOTREACHED
	return 2
    fi
}
