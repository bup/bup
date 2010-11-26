#!/usr/bin/env bash
. wvtest.sh
#set -e

TOP="$(pwd)"
export BUP_DIR="$TOP/buptest.tmp"

bup()
{
    "$TOP/bup" "$@"
}

# Very simple metadata tests -- "make install" to a temp directory,
# then check that bup meta can reproduce the metadata correctly
# (according to coreutils stat) via create, extract, start-extract,
# and finish-extract.  The current tests are crude, and this does not
# test devices, varying users/groups, acls, attrs, etc.
WVSTART "meta"

genstat()
{
  (
    export PATH="${TOP}:${PATH}" # pick up bup
    find . | sort | xargs bup xstat --exclude-fields ctime
  )
}

# Create a test tree and collect its info via stat(1).
(
  set -e
  rm -rf "${TOP}/bupmeta.tmp"
  mkdir -p "${TOP}/bupmeta.tmp"
  make DESTDIR="${TOP}/bupmeta.tmp/src" install
  mkdir "${TOP}/bupmeta.tmp/src/misc"
  cp -a cmd/bup-* "${TOP}/bupmeta.tmp/src/misc/"
  cd "${TOP}/bupmeta.tmp/src"
  WVPASS genstat >../src-stat
) || WVFAIL

# Use the test tree to check bup meta.
(
  WVPASS cd "${TOP}/bupmeta.tmp"
  WVPASS bup meta --create --recurse --file src.meta src
  WVPASS mkdir src-restore
  WVPASS cd src-restore
  WVPASS bup meta --extract --file ../src.meta
  WVPASS test -d src
  (cd src && genstat >../../src-restore-stat) || WVFAIL
  WVPASS diff -u5 ../src-stat ../src-restore-stat
  WVPASS rm -rf src
  WVPASS bup meta --start-extract --file ../src.meta
  WVPASS test -d src
  WVPASS bup meta --finish-extract --file ../src.meta
  (cd src && genstat >../../src-restore-stat) || WVFAIL
  WVPASS diff -u5 ../src-stat ../src-restore-stat
)

exit 0
