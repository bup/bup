#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?
export BUP_DIR="$tmpdir/bup"
D="$tmpdir/data"

bup() { "$top/bup" "$@"; }

WVSTART "remove file"
# Fixed in commit 8585613c1f45f3e20feec00b24fc7e3a948fa23e ("Store
# metadata in the index....")
WVPASS mkdir "$D"
WVPASS bup init
WVPASS echo "content" > "$D"/foo
WVPASS echo "content" > "$D"/bar
WVPASS bup tick
WVPASS bup index -ux "$D"
WVPASS bup save -n save-fail-missing "$D"
WVPASS echo "content" > "$D"/baz
WVPASS bup tick
WVPASS bup index -ux "$D"
WVPASS rm "$D"/foo
# When "bup tick" is removed above, this may fail (complete with warning),
# since the ctime/mtime of "foo" might be pushed back:
WVPASS bup save -n save-fail-missing "$D"
# when the save-call failed, foo is missing from output, since only
# then bup notices, that it was removed:
WVPASSEQ "$(bup ls -A save-fail-missing/latest/$TOP/$D/)" "bar
baz
foo"
# index/save again
WVPASS bup tick
WVPASS bup index -ux "$D"
WVPASS bup save -n save-fail-missing "$D"
# now foo is gone:
WVPASSEQ "$(bup ls -A save-fail-missing/latest/$TOP/$D/)" "bar
baz"


# TODO: Test for racecondition between reading a file and reading its metadata?

WVSTART "remove dir"
WVPASS rm -r "$D"
WVPASS mkdir "$D"
WVPASS rm -r "$BUP_DIR"
WVPASS bup init
WVPASS mkdir "$D"/foo
WVPASS mkdir "$D"/bar
WVPASS bup tick
WVPASS bup index -ux "$D"
WVPASS bup save -n save-fail-missing "$D"
WVPASS touch "$D"/bar
WVPASS mkdir "$D"/baz
WVPASS bup tick
WVPASS bup index -ux "$D"
WVPASS rmdir "$D"/foo
# with directories, bup notices that foo is missing, so it fails
# (complete with delayed error)
WVFAIL bup save -n save-fail-missing "$D"
# ...but foo is still saved since it was just fine in the index
WVPASSEQ "$(bup ls -AF save-fail-missing/latest/$TOP/$D/)" "bar/
baz/
foo/"
# Index again:
WVPASS bup tick
WVPASS bup index -ux "$D"
# no non-zero-exitcode anymore:
WVPASS bup save -n save-fail-missing "$D"
# foo is now gone
WVPASSEQ "$(bup ls -AF save-fail-missing/latest/$TOP/$D/)" "bar/
baz/"

WVPASS rm -rf "$tmpdir"

