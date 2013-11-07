# Assumes shell is Bash, and pipefail is set.

force-delete()
{
    local rc=0
    # Try *hard* to delete $@.  Among other things, some systems have
    # r-xr-xr-x for root and other system dirs.
    rm -rf "$@" # Maybe we'll get lucky.
    for f in "$@"; do
        test -e "$f" || continue
        if test "$(type -p setfacl)"; then
            setfacl -Rb "$f"
        fi
        if test "$(type -p chattr)"; then
            chattr -R -aisu "$f"
        fi
        chmod -R u+rwX "$f"
        rm -r "$f"
        if test -e "$f"; then
            rc=1
            find "$f" -ls
            lsattr -aR "$f"
            getfacl -R "$f"
        fi
    done
    return $rc
}

realpath()
{
    test "$#" -eq 1 || return $?
    local script_home=$(cd "$(dirname $0)" && pwd)
    echo "$1" | \
        PYTHONPATH="${script_home}/../lib" python -c \
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
