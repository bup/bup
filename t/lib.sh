# Assumes shell is Bash, and pipefail is set.

bup_t_lib_script_home=$(cd "$(dirname $0)" && pwd)

force-delete()
{
    "$bup_t_lib_script_home/force-delete" "$@"
}

realpath()
{
    test "$#" -eq 1 || return $?
    echo "$1" | \
        PYTHONPATH="$bup_t_lib_script_home/../lib" python -c \
        "import sys, bup.helpers; print bup.helpers.realpath(sys.stdin.readline())" \
        || return $?
}

current-filesystem()
{
    local kernel="$(uname -s)" || return $?
    case "$kernel" in
        NetBSD)
            df -G . | sed -En 's/.* ([^ ]*) fstype.*/\1/p'
            ;;
        SunOS)
            df -g . | sed -En 's/.* ([^ ]*) fstype.*/\1/p'
            ;;
        *)
            df -T . | awk 'END{print $2}'
    esac
}

path-filesystems()
(
    # Return filesystem for each dir from $1 to /.
    # Perhaps for /foo/bar, "ext4\next4\nbtrfs\n".
    test "$#" -eq 1 || exit $?
    cd "$1" || exit $?
    current-filesystem || exit $?
    dir="$(pwd)" || exit $?
    while test "$dir" != /; do
        cd .. || exit $?
        dir="$(pwd)" || exit $?
        current-filesystem || exit $?
    done
    exit 0
)

escape-erx()
{
    sed 's/[][\.|$(){?+*^]/\\&/g' <<< "$*"
}
