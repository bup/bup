#!/usr/bin/env bash
. ./wvtest-bup.sh

set -e -o pipefail

top="$(pwd)"
tmpdir="$(wvmktempdir)"
export BUP_DIR="$tmpdir/bup"
D="$tmpdir/data"

bup() { "$top/bup" "$@"; }

WVSTART "remove file"
# Fixed in commit 8585613c1f45f3e20feec00b24fc7e3a948fa23e ("Store
# metadata in the index....")
mkdir "$D"
bup init
echo "content" > "$D"/foo
echo "content" > "$D"/bar
bup index -ux "$D"
bup save -n save-fail-missing "$D"
echo "content" > "$D"/baz
bup index -ux "$D"
rm "$D"/foo
WVFAIL bup save -n save-fail-missing "$D"
WVPASSEQ "$(bup ls -a save-fail-missing/latest/$TOP/$D/)" "bar
baz"

# TODO: Test for racecondition between reading a file and reading its metadata?

WVSTART "remove dir"
rm -r "$D"
mkdir "$D"
rm -r "$BUP_DIR"
bup init
mkdir "$D"/foo
mkdir "$D"/bar
bup index -ux "$D"
bup save -n save-fail-missing "$D"
touch "$D"/bar
mkdir "$D"/baz
bup index -ux "$D"
rmdir "$D"/foo
WVFAIL bup save -n save-fail-missing "$D"
WVPASSEQ "$(bup ls -a save-fail-missing/latest/$TOP/$D/)" "bar/
baz/"

rm -rf "$tmpdir"
