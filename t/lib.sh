# Assumes shell is Bash.

actually-root()
{
    test "$(whoami)" == root -a -z "$FAKEROOTKEY"
}

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
