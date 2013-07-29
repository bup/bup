# Assumes shell is Bash.

force-delete()
{
    # Try *hard* to delete $@.  Among other things, some systems have
    # r-xr-xr-x for root and other system dirs.
    rm -rf "$@" # Maybe we'll get lucky.
    for f in "$@"; do
        test -e "$@" || continue
        chmod -R u+w "$@"
        if [[ $(uname) =~ Linux ]]; then
            chattr -fR = "$@"
            setfacl -Rb "$@"
        fi
        rm -r "$@"
        if test -e "$@"; then
            return 1
        fi
    done
}

realpath()
(
    set -e;
    test "$#" -eq 1
    script_home=$(cd "$(dirname $0)" && pwd)
    echo "$1" | \
        PYTHONPATH="${script_home}/../lib" python -c \
        "import sys, bup.helpers; print bup.helpers.realpath(sys.stdin.readline())"
)
