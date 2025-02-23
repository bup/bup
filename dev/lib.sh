# Assumes shell is Bash, and pipefail is set.

# Assumes this is always loaded while pwd is still the source tree root
bup_dev_lib_top=$(pwd) || exit $?

bup_exit_failure=2

bup-cfg-py() { "$bup_dev_lib_top/dev/python" "$@"; }
bup-python() { "$bup_dev_lib_top/dev/bup-python" "$@"; }

force-delete()
{
    "$bup_dev_lib_top/dev/force-delete" "$@"
}

resolve-parent()
{
    test "$#" -eq 1 || return $?
    echo "$1" | \
        bup-python \
            -c "import sys, bup.helpers; print(bup.helpers.resolve_parent(sys.stdin.readline()))" \
        || return $?
}

path-filesystems()
(
    # Return filesystem for each dir from $1 to /.
    # Perhaps for /foo/bar, "ext4\next4\nbtrfs\n".
    test "$#" -eq 1 || exit $?
    cd "$1" || exit $?
    "$bup_dev_lib_top/dev/path-fs" . || exit $?
    dir="$(pwd)" || exit $?
    while test "$dir" != /; do
        cd .. || exit $?
        dir="$(pwd)" || exit $?
        "$bup_dev_lib_top/dev/path-fs" . || exit $?
    done
    exit 0
)

escape-erx()
{
    sed 's/[][\.|$(){?+*^]/\\&/g' <<< "$*"
}
