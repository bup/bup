# Include in your test script like this:
#
#   #!/usr/bin/env bash
#   . ./wvtest-bup.sh

. ./wvtest.sh

_wvtop="$(pwd)"

wvmktempdir ()
{
    local script_name="$(basename $0)"
    mkdir -p "$_wvtop/t/tmp" || exit $?
    mktemp -d "$_wvtop/t/tmp/$script_name-XXXXXXX" || exit $?
}

wvmkmountpt ()
{
    local script_name="$(basename $0)"
    mkdir -p "$_wvtop/t/mnt" || exit $?
    mktemp -d "$_wvtop/t/mnt/$script_name-XXXXXXX" || exit $?
}
