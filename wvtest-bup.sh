# Include in your test script like this:
#
#   #!/usr/bin/env bash
#   . ./wvtest-bup.sh

. ./wvtest.sh

_wvtop="$(pwd)"

wvmktempdir ()
(
    script_name="$(basename $0)"
    set -e -o pipefail
    mkdir -p "$_wvtop/t/tmp"
    mktemp -d "$_wvtop/t/tmp/$script_name-XXXXXXX"
)

wvmkmountpt ()
(
    script_name="$(basename $0)"
    set -e -o pipefail
    mkdir -p "$_wvtop/t/mnt"
    mktemp -d "$_wvtop/t/mnt/$script_name-XXXXXXX"
)
