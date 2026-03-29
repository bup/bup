
# If not test-specific, see dev/lib.sh.

# bup test lib: all code must assume "set +e" may or may not be in
# effect, and the state of pipefail is unspecified.

btl-ent-oid()
{
    # Return the oid from a git ls-tree line provided as either an
    # argument or on stdin. Does not validate.
    case $# in
        0) local ls_tree_line="$(</dev/stdin)" ;;
        1) local ls_tree_line="$1" ;;
        *) return 2 ;;
    esac
    oid="${ls_tree_line%%$'\t'*}"
    echo "${oid##* }"
}

btl-display-file()
{
    local name="$1"
    printf -- "----- \"%q\" content below -----\n" "$name" || exit $?
    cat "$name" || exit $?
    printf -- "----- \"%q\" content above -----\n" "$name" || exit $?
}


# out-to, err-to, and both-to allow redirections of just stdout or
# stderr when using "wrapper" commands like WVPASS, WVFAIL, ...  For
# example
#
#     WVPASS err-to err.log some --random --comand
#     WVPASS grep ... err.log
#
# This avoids capturing the WV command's output in the log which
# happens for something like "WVPASS ... > err.log".  This also makes
# sure the comand doesn't return until the output is finished, which
# isn't the case for a process substitution like this:
#
#     WVPASS eval "some --command 2> >(tee err.log)"
#

out-to()
{
    test $# -gt 1 || { echo 'Usage: out-to OUT cmd ...' 1>&2; exit 2; }
    local out="$1"
    shift
    "$@" | tee "$out"
    return "${PIPESTATUS[0]}"
}

err-to()
{
    test $# -gt 1 || { echo 'Usage: err-to ERR cmd ...' 1>&2; exit 2; }
    local err="$1" fd rc
    shift
    { "$@" 2>&1 >&${fd} {fd}>&- | tee "$err" {fd}>&-; rc="${PIPESTATUS[0]}"; } \
        {fd}>&1
    : {fd}>&-
    return $rc
}

both-to()
{
    test $# -gt 2 || { echo 'Usage: both-to OUT ERR cmd ...' 1>&2; exit 2; }
    local out="$1" err="$2"
    shift 2
    err-to "$err" out-to "$out" "$@"
}
