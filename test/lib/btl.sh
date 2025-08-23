
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
