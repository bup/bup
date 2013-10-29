# Assumes shell is Bash.

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
