
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
