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
bup tick
bup index -ux "$D"
bup save -n save-fail-missing "$D"
echo "content" > "$D"/baz
bup tick
bup index -ux "$D"
rm "$D"/foo
# When "bup tick" is removed above, this may fail (complete with warning),
# since the ctime/mtime of "foo" might be pushed back:
WVPASS bup save -n save-fail-missing "$D"
# when the save-call failed, foo is missing from output, since only
# then bup notices, that it was removed:
WVPASSEQ "$(bup ls -a save-fail-missing/latest/$TOP/$D/)" "bar
baz
foo"
# index/save again
bup tick
bup index -ux "$D"
WVPASS bup save -n save-fail-missing "$D"
# now foo is gone:
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
bup tick
bup index -ux "$D"
bup save -n save-fail-missing "$D"
touch "$D"/bar
mkdir "$D"/baz
bup tick
bup index -ux "$D"
rmdir "$D"/foo
# with directories, bup notices that foo is missing, so it fails
# (complete with delayed error)
WVFAIL bup save -n save-fail-missing "$D"
# ... so "foo" is absent from "bup ls"
WVPASSEQ "$(bup ls -a save-fail-missing/latest/$TOP/$D/)" "bar/
baz/"
# Index again:
bup tick
bup index -ux "$D"
# no non-zero-exitcode anymore:
WVPASS bup save -n save-fail-missing "$D"
# foo is (still...) missing, of course:
WVPASSEQ "$(bup ls -a save-fail-missing/latest/$TOP/$D/)" "bar/
baz/"

rm -rf "$tmpdir"
