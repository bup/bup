# Include in your test script like this:
#
#   #!/usr/bin/env bash
#   . ./wvtest-bup.sh

. ./wvtest.sh

_wvtop="$(pwd)"

wvmktempdir ()
{
    local script_name="$(basename $0)"
    mkdir -p "$_wvtop/test/tmp" || exit $?
    mktemp -d "$_wvtop/test/tmp/$script_name-XXXXXXX" || exit $?
}

wvmkmountpt ()
{
    local script_name="$(basename $0)"
    mkdir -p "$_wvtop/test/mnt" || exit $?
    mktemp -d "$_wvtop/test/mnt/$script_name-XXXXXXX" || exit $?
}
